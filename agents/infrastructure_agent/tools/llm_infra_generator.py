import os
import re
import subprocess
import json
from jinja2 import Template
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import IaCReadyEvent
from shared_modules.kafka_event_bus.topics import IAC_READY

REPO_BASE_PATH = "/tmp/gitops_repos"
PROMPT_PATH_TF = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "shared_modules", "llm_config", "prompts", "terraform_prompt.txt"
)

def read_prompt_template(path):
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())

def strip_markdown_blocks(content: str) -> str:
    content = re.sub(r"(?s)```(?:terraform|hcl|text)?\s*(.*?)```", r"\1", content)
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
    try:
        config = state.repo_context.config or {}
        infra_cfg = config.get("infrastructure", {})
        deployment_cfg = config.get("deployment", {})
        tool = infra_cfg.get("tool", "terraform").lower()
        path = infra_cfg.get("path", "infra/")
        provider = deployment_cfg.get("provider", "aws")
        region = deployment_cfg.get("region", "us-east-1")
        repo_name = event.get("repo") or event.get("repo_context", {}).get("repo") or "Sample_fullstack_project"

        context = f"Deployment: {deployment_cfg}\nInfrastructure: {infra_cfg}\nCloud Provider: {provider}\nRegion: {region}\nFull YAML: {config}"
        base_path = os.path.join(REPO_BASE_PATH, repo_name, path)
        os.makedirs(base_path, exist_ok=True)

        status = "failed"
        resources = []
        logs = ""
        outputs = {}

        if tool == "terraform":
            prompt_template = read_prompt_template(PROMPT_PATH_TF)
            prompt = prompt_template.render(context=context)
            logger.info("[Infra Agent] Sending LLM prompt for Terraform infrastructure generation")
            response = run_prompt(prompt, temperature=0.3, max_tokens=10000)
            clean_response = strip_markdown_blocks(response)
            tf_files = split_tf_files(clean_response)
            logger.info(f"[Infra Agent] Terraform files returned by LLM: {list(tf_files.keys())}")

            expected_files = {"provider.tf", "main.tf", "variables.tf", "outputs.tf"}
            missing = expected_files - tf_files.keys()
            if missing:
                logger.warning(f"[Infra Agent] Missing Terraform files from LLM response: {missing}")

            written_files = []

            for fname in expected_files:
                content = tf_files.get(fname)
                if content:
                    with open(os.path.join(base_path, fname), "w") as f:
                        f.write(content.strip())
                    written_files.append(fname)

            try:
                logger.info("[Infra Agent] Running terraform init")
                subprocess.run(["terraform", "init", "-input=false", "-no-color"], cwd=base_path, check=True)

                logger.info("[Infra Agent] Running terraform validate")
                subprocess.run(["terraform", "validate", "-no-color"], cwd=base_path, check=True)

                logger.info("[Infra Agent] Running terraform apply")
                subprocess.run(["terraform", "apply", "-auto-approve", "-input=false", "-no-color"], cwd=base_path, check=True)

                # Fetch outputs
                try:
                    logger.info("[Infra Agent] Fetching Terraform outputs")
                    result = subprocess.run(["terraform", "output", "-json"], cwd=base_path, check=True, capture_output=True, text=True)
                    tf_output_json = result.stdout
                    outputs = {k: v["value"] for k, v in json.loads(tf_output_json).items()}
                    logger.info(f"[Infra Agent] Extracted outputs: {outputs}")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"[Infra Agent] terraform output failed: {e}")
                    outputs = {}

                status = "success"
                resources = ["terraform"]
                logs = f"Terraform files applied successfully: {written_files}"

            except subprocess.CalledProcessError as e:
                logger.error(f"[Infra Agent] Terraform execution failed: {e}")
                return {
                    "status": "failed",
                    "resources": [],
                    "outputs": {},
                    "logs": f"Terraform failed: {e}"
                }

        elif tool == "cloudformation":
            cloudformation_prompt = (
                "You are a cloud infrastructure automation expert. "
                "Based on the following application code or description, generate a complete AWS CloudFormation YAML template "
                "to provision and deploy the application. Output only the raw YAML, no markdown or commentary.\n" +
                context
            )
            logger.info("[Infra Agent] Sending LLM prompt for CloudFormation infrastructure generation")
            response = run_prompt(cloudformation_prompt, temperature=0.3)
            clean_response = strip_markdown_blocks(response)
            cf_file = os.path.join(base_path, "cloudformation.yaml")
            with open(cf_file, "w") as f:
                f.write(clean_response.strip())
            status = "success"
            resources = ["cloudformation"]
            logs = f"CloudFormation file written: {cf_file}"
        else:
            logger.error(f"[Infra Agent] Unsupported infrastructure tool: {tool}")
            logs = f"Unsupported tool: {tool}"
            return {"status": "failed", "resources": [], "outputs": {}, "logs": logs}

        # 📦 Publish Kafka event
        iac_event = IaCReadyEvent(
            repo=repo_name,
            resources=resources,
            status=status,
            logs=logs,
            outputs=outputs,
            agent="iac_agent"
        )
        try:
            publish_event(IAC_READY, iac_event.model_dump())
            logger.info(f"[Kafka] IaCReadyEvent published for repo: {repo_name}")
        except Exception as e:
            logger.error(f"[Kafka] Failed to publish IaCReadyEvent: {e}")

        return {
            "status": status,
            "resources": resources,
            "outputs": outputs,
            "logs": logs
        }

    except Exception as e:
        logger.error(f"[Infra Agent] Failed to generate infrastructure: {e}")
        return {"status": "failed", "resources": [], "outputs": {}, "logs": str(e)}
