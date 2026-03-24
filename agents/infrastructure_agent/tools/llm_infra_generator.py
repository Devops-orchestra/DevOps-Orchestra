"""
Generate infrastructure as code (Terraform, CloudFormation, ARM, GCP DM) with LLM.
Runs init + plan only; does NOT apply. Plan and generated code are sent to the user
via Slack. The deployment agent applies infra (and e.g. Lambda package) only after
the user replies yes/apply in Slack.
"""
import os
import re
import subprocess
import json
from typing import Optional

from jinja2 import Template
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import IaCReadyEvent
from shared_modules.kafka_event_bus.topics import IAC_READY

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")
PROMPT_PATH_TF = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "shared_modules", "llm_config", "prompts", "terraform_prompt.txt"
)

SUPPORTED_TOOLS = ("terraform", "cloudformation", "arm", "gcp")


def _infra_base_path(event: dict, state: DevOpsAgentState) -> str:
    """Return infra directory path (same repo clone as pipeline)."""
    repo_name = event.get("repo") or event.get("repo_context", {}).get("repo") or "repo"
    branch = (state.repo_context.branch or "main").replace("/", "_")
    config = state.repo_context.config or {}
    path = config.get("infrastructure", {}).get("path", "infra")
    path = path.rstrip("/")
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch}", path)


def read_prompt_template(path: str) -> Template:
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())


def strip_markdown_blocks(content: str, patterns: Optional[list] = None) -> str:
    if patterns is None:
        patterns = [r"(?s)```(?:terraform|hcl|json|yaml|text)?\s*(.*?)```"]
    for pat in patterns:
        content = re.sub(pat, r"\1", content)
    return content.strip()


def split_tf_files(clean_response: str) -> dict:
    files = {}
    current_file = None
    current_lines = []

    for line in clean_response.splitlines():
        stripped = line.strip().lower()
        if stripped in {"provider.tf", "main.tf", "variables.tf", "outputs.tf"}:
            if current_file and current_lines:
                files[current_file] = "\n".join(current_lines).strip()
            current_file = stripped
            current_lines = []
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        files[current_file] = "\n".join(current_lines).strip()

    if not files:
        files["main.tf"] = clean_response.strip()

    return files


def generate_infrastructure_with_llm(event: dict, state: DevOpsAgentState) -> dict:
    """
    Generate IaC with LLM and run init + plan (no apply). Returns status="plan_ready"
    with plan_output for the user; apply is run only after user accepts via Slack.
    Supports: terraform (default), cloudformation, arm, gcp.
    """
    try:
        config = state.repo_context.config or {}
        infra_cfg = config.get("infrastructure", {})
        deployment_cfg = config.get("deployment", {})
        tool = (infra_cfg.get("tool") or "terraform").strip().lower()
        if tool not in SUPPORTED_TOOLS:
            tool = "terraform"
        provider = deployment_cfg.get("provider", "aws")
        region = deployment_cfg.get("region", "us-east-1")
        repo_name = event.get("repo") or event.get("repo_context", {}).get("repo") or "repo"

        context = (
            f"Deployment: {deployment_cfg}\nInfrastructure: {infra_cfg}\n"
            f"Cloud Provider: {provider}\nRegion: {region}\n"
            f"Full config: {config}\nApplication context: {state.llm_context_memory or ''}"
        )
        base_path = _infra_base_path(event, state)
        os.makedirs(base_path, exist_ok=True)

        plan_output = ""
        logs = ""

        if tool == "terraform":
            prompt_template = read_prompt_template(PROMPT_PATH_TF)
            prompt = prompt_template.render(context=context)
            logger.info("[Infra Agent] Generating Terraform with LLM")
            response = run_prompt(prompt, temperature=0.3, max_tokens=10000)
            clean_response = strip_markdown_blocks(response)
            tf_files = split_tf_files(clean_response)
            expected_files = {"provider.tf", "main.tf", "variables.tf", "outputs.tf"}
            for fname in expected_files:
                content = tf_files.get(fname)
                if content:
                    with open(os.path.join(base_path, fname), "w") as f:
                        f.write(content.strip())
            try:
                subprocess.run(
                    ["terraform", "init", "-input=false", "-no-color"],
                    cwd=base_path, check=True, capture_output=True, text=True, timeout=120
                )
                subprocess.run(
                    ["terraform", "validate", "-no-color"],
                    cwd=base_path, check=True, capture_output=True, text=True
                )
                result = subprocess.run(
                    ["terraform", "plan", "-no-color", "-input=false"],
                    cwd=base_path, capture_output=True, text=True, timeout=120
                )
                plan_output = (result.stdout or "") + (result.stderr or "")
                logs = f"Terraform init and plan completed. Review the plan above."
                if result.returncode != 0:
                    return {"status": "failed", "plan_output": plan_output, "logs": plan_output, "infra_path": base_path, "tool": tool}
            except subprocess.CalledProcessError as e:
                logs = (e.stdout or "") + (e.stderr or str(e))
                return {"status": "failed", "plan_output": logs, "logs": logs, "infra_path": base_path, "tool": tool}

        elif tool == "cloudformation":
            prompt = (
                "You are an AWS CloudFormation expert. Generate a complete CloudFormation YAML template "
                "to provision infrastructure for the application. Output only raw YAML, no markdown.\n\n" + context
            )
            response = run_prompt(prompt, temperature=0.3, max_tokens=8000)
            clean = strip_markdown_blocks(response)
            out_file = os.path.join(base_path, "cloudformation.yaml")
            with open(out_file, "w") as f:
                f.write(clean.strip())
            plan_output = clean[:4000] + "\n...(truncated)" if len(clean) > 4000 else clean
            logs = f"CloudFormation template written to {out_file}. Review above."

        elif tool == "arm":
            prompt = (
                "You are an Azure Resource Manager (ARM) expert. Generate a complete ARM template (JSON) "
                "to provision infrastructure for the application. Output only valid JSON, no markdown.\n\n" + context
            )
            response = run_prompt(prompt, temperature=0.3, max_tokens=8000)
            clean = strip_markdown_blocks(response)
            out_file = os.path.join(base_path, "template.json")
            with open(out_file, "w") as f:
                f.write(clean.strip())
            plan_output = clean[:4000] + "\n...(truncated)" if len(clean) > 4000 else clean
            logs = f"ARM template written to {out_file}. Review above."

        elif tool == "gcp":
            prompt = (
                "You are a Google Cloud Deployment Manager expert. Generate a complete Deployment Manager "
                "YAML config (config + schema if needed) to provision infrastructure. Output only raw YAML, no markdown.\n\n" + context
            )
            response = run_prompt(prompt, temperature=0.3, max_tokens=8000)
            clean = strip_markdown_blocks(response)
            out_file = os.path.join(base_path, "deployment.yaml")
            with open(out_file, "w") as f:
                f.write(clean.strip())
            plan_output = clean[:4000] + "\n...(truncated)" if len(clean) > 4000 else clean
            logs = f"GCP Deployment Manager config written to {out_file}. Review above."

        else:
            return {"status": "failed", "plan_output": "", "logs": f"Unsupported tool: {tool}", "infra_path": base_path, "tool": tool}

        # Plan is returned to pipeline; user approves via Slack before apply_infrastructure() is called.
        return {
            "status": "plan_ready",
            "plan_output": plan_output,
            "logs": logs,
            "infra_path": base_path,
            "tool": tool,
        }

    except Exception as e:
        logger.error(f"[Infra Agent] Failed to generate infrastructure: {e}")
        return {"status": "failed", "plan_output": "", "logs": str(e), "infra_path": "", "tool": "terraform"}


def apply_infrastructure(infra_path: str, tool: str, repo_name: str = "repo") -> dict:
    """
    Run apply/create after user accepted the plan. Call this only when user confirms via Slack.
    """
    if not infra_path or not os.path.isdir(infra_path):
        return {"status": "failed", "outputs": {}, "logs": f"Invalid infra path: {infra_path}"}

    tool = (tool or "terraform").lower()
    outputs = {}
    logs = ""

    try:
        if tool == "terraform":
            result = subprocess.run(
                ["terraform", "apply", "-auto-approve", "-input=false", "-no-color"],
                cwd=infra_path, capture_output=True, text=True, timeout=600
            )
            logs = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0:
                return {"status": "failed", "outputs": {}, "logs": logs}
            try:
                out = subprocess.run(
                    ["terraform", "output", "-json"],
                    cwd=infra_path, capture_output=True, text=True, timeout=10
                )
                if out.returncode == 0:
                    outputs = {k: v.get("value") for k, v in json.loads(out.stdout).items()}
            except Exception:
                pass
            status = "success"

        elif tool == "cloudformation":
            cf_file = os.path.join(infra_path, "cloudformation.yaml")
            if not os.path.isfile(cf_file):
                return {"status": "failed", "outputs": {}, "logs": f"Missing {cf_file}"}
            result = subprocess.run(
                ["aws", "cloudformation", "create-stack", "--template-body", f"file://{cf_file}", "--stack-name", f"{repo_name}-stack"],
                capture_output=True, text=True, timeout=300
            )
            logs = (result.stdout or "") + (result.stderr or "")
            status = "success" if result.returncode == 0 else "failed"

        elif tool == "arm":
            template_file = os.path.join(infra_path, "template.json")
            if not os.path.isfile(template_file):
                return {"status": "failed", "outputs": {}, "logs": f"Missing {template_file}"}
            result = subprocess.run(
                ["az", "deployment", "group", "create", "--resource-group", f"{repo_name}-rg", "--template-file", template_file],
                capture_output=True, text=True, timeout=600
            )
            logs = (result.stdout or "") + (result.stderr or "")
            status = "success" if result.returncode == 0 else "failed"

        elif tool == "gcp":
            dep_file = os.path.join(infra_path, "deployment.yaml")
            if not os.path.isfile(dep_file):
                return {"status": "failed", "outputs": {}, "logs": f"Missing {dep_file}"}
            result = subprocess.run(
                ["gcloud", "deployment-manager", "deployments", "create", f"{repo_name}-dm", "--config", dep_file],
                capture_output=True, text=True, timeout=600
            )
            logs = (result.stdout or "") + (result.stderr or "")
            status = "success" if result.returncode == 0 else "failed"

        else:
            return {"status": "failed", "outputs": {}, "logs": f"Unsupported tool for apply: {tool}"}

        if status == "success":
            try:
                iac_event = IaCReadyEvent(
                    repo=repo_name,
                    resources=[tool],
                    status="success",
                    logs=logs[-2000:],
                    outputs=outputs,
                    agent="iac_agent"
                )
                publish_event(IAC_READY, iac_event.model_dump())
            except Exception as e:
                logger.warning(f"[Infra Agent] Publish IaCReadyEvent: {e}")

        return {"status": status, "outputs": outputs, "logs": logs}

    except subprocess.TimeoutExpired:
        return {"status": "failed", "outputs": {}, "logs": "Apply timed out."}
    except Exception as e:
        logger.error(f"[Infra Agent] Apply failed: {e}")
        return {"status": "failed", "outputs": {}, "logs": str(e)}
