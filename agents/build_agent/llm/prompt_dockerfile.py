import re
from shared_modules.utils.logger import logger
from jinja2 import Template
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.state.devops_state import DevOpsAgentState
import os

def read_prompt_template():
    path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "shared_modules", "llm_config", "prompts", "docker_prompt.txt"
    )
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())

def strip_markdown_blocks(content: str) -> str:
    """
    Removes markdown formatting like ```dockerfile, ```text, and any 'Dockerfile' header.
    """
    # Remove all ``` blocks with or without language tag
    content = re.sub(r"(?s)```(?:\w+)?\s*(.*?)```", r"\1", content)

    # Remove 'Dockerfile' or similar headings
    content = re.sub(r"^\s*Dockerfile\s*", "", content, flags=re.IGNORECASE)

    return content.strip()

def generate_dockerfile_with_llm(state: DevOpsAgentState) -> str:
    prompt_template = read_prompt_template()
    prompt = prompt_template.render(context=state.llm_context_memory)

    logger.info("[Build Agent] Sending LLM prompt for Dockerfile generation")
    response = run_prompt(prompt, temperature=0.3)

    clean_dockerfile = strip_markdown_blocks(response)
    logger.info("[Build Agent] Cleaned LLM output for Dockerfile")

    return clean_dockerfile
