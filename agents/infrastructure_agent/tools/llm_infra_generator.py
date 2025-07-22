import os
import re
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
# (If you add a cloudformation prompt, add PROMPT_PATH_CF here)

def read_prompt_template(path):
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())

def strip_markdown_blocks(content: str) -> str:
    """
    Removes markdown formatting like ```terraform, ```text, and any file headers.
    """
    # Remove all ``` blocks with or without language tag
    content = re.sub(r"(?s)```(?:terraform|hcl|text)?\s*(.*?)```", r"\1", content)
    # Remove any file headers like 'main.tf', 'provider.tf', etc. at the start of a line
    content = re.sub(r"^(main\.tf|provider\.tf|variables\.tf|outputs\.tf)\s*", "", content, flags=re.IGNORECASE | re.MULTILINE)
    return content.strip()

def split_tf_files(clean_response: str) -> dict:
    """
    Splits the cleaned LLM output into tf files by detecting file headers or blocks.
    Returns a dict: {filename: content}
    """
    # Find all file blocks by header (e.g., provider.tf, main.tf, etc.)
    pattern = r"(?im)^\s*(provider\.tf|main\.tf|variables\.tf|outputs\.tf)\s*\n(.*?)(?=^\s*(?:provider\.tf|main\.tf|variables\.tf|outputs\.tf)\s*\n|\Z)"
    matches = re.findall(pattern, clean_response, re.DOTALL | re.MULTILINE)
    files = {}
    for fname, content in matches:
        files[fname.strip().lower()] = content.strip()
    # If no headers found, treat the whole response as main.tf
    if not files:
        files["main.tf"] = clean_response.strip()
    return files

def generate_infrastructure_with_llm(event: dict, state: DevOpsAgentState) -> dict:
    """
    Generates Terraform or CloudFormation using LLM and saves files to the correct path.
    Uses config from state.repo_context.config.
    Publishes IaCReadyEvent to Kafka after completion.
    """
    try:
        config = state.repo_context.config or {}
        infra_cfg = config.get("infrastructure", {})
        deployment_cfg = config.get("deployment", {})
        tool = infra_cfg.get("tool", "terraform").lower()
        path = infra_cfg.get("path", "infra/")
        provider = deployment_cfg.get("provider", "aws")
        region = deployment_cfg.get("region", "us-east-1")
        repo_name = event.get("repo") or event.get("repo_context", {}).get("repo") or "Sample_fullstack_project"
        # Compose context for LLM
        context = f"Deployment: {deployment_cfg}\nInfrastructure: {infra_cfg}\nCloud Provider: {provider}\nRegion: {region}\nFull YAML: {config}"
        # Prepare output directory
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
            written_files = []
            for fname in ["provider.tf", "main.tf", "variables.tf", "outputs.tf"]:
                content = tf_files.get(fname)
                if content:
                    with open(os.path.join(base_path, fname), "w") as f:
                        f.write(content.strip())
                    written_files.append(fname)
            status = "success"
            resources = ["terraform"]
            logs = f"Terraform files written: {written_files}"
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
        # Publish IaCReadyEvent to Kafka
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