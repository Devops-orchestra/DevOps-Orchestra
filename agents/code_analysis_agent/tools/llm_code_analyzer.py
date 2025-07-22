# File: agents/code_analysis_agent/tools/llm_code_analyzer.py

import os
import glob
from jinja2 import Template
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import CodeAnalysisEvent
from shared_modules.kafka_event_bus.topics import CODE_ANALYSIS
from agents.code_analysis_agent.tools.llm_utils import parse_llm_summary

SUPPORTED_EXTENSIONS = ["*.py", "*.js", "*.java", "*.cpp", "*.c", "*.html", "*.css", "*.ts"]

REPO_BASE_PATH = "/tmp/gitops_repos"

def read_prompt_template():
    path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "shared_modules", "llm_config", "prompts", "code_analysis_prompt.txt"
    )
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())

def analyze_code_with_llm(event: dict, state: DevOpsAgentState = None):
    repo = event['repo_context']["repo"]
    branch = event['repo_context']["branch"]
    commit_id = event['repo_context']["commit"]
    repo_path = os.path.join(REPO_BASE_PATH, repo)
    file_limit = 10
    llm_model = "llama-3.3-70b-versatile"
    logger.info(f"Starting LLM code analysis for repo: {repo_path}")
    prompt_template = read_prompt_template()

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(glob.glob(os.path.join(repo_path, "**", ext), recursive=True))
    files = files[:file_limit]

    results = []
    combined_context = ""

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            continue

        prompt = prompt_template.render(
            filename=os.path.basename(file_path),
            file_contents=code[:3000]
        )

        try:
            llm_response = run_prompt(
                prompt=prompt,
                model=llm_model,
                temperature=0.2,
                max_tokens=1024
            )
        except Exception as e:
            logger.error(f"LLM failed on {file_path}: {e}")
            llm_response = f"Error analyzing {file_path}: {e}"

        results.append({
            "file": file_path,
            "analysis": llm_response
        })

        # Add to context memory
        combined_context += f"\n# File: {os.path.relpath(file_path, repo_path)}\n{code[:3000]}\n"

    # If state is passed, update it
    if state is not None:
        state.llm_context_memory = combined_context

    # Parse and update state, publish event
    if results:
        analysis_text = results[0]["analysis"]
        parsed = parse_llm_summary(analysis_text)
        state.code_analysis.passed = parsed["passed"]
        state.code_analysis.errors = parsed["errors"]
        state.code_analysis.warnings = parsed["warnings"]
        state.code_analysis.logs = parsed["notes"]
        logger.info(f"[Code Analysis] Errors: {len(parsed['errors'])}, Warnings: {len(parsed['warnings'])}")
        code_analysis_event = CodeAnalysisEvent(
            repo=repo,
            passed=parsed["passed"],
            errors=parsed["errors"],
            warnings=parsed["warnings"],
            notes=parsed["notes"]
        )
        try:
            publish_event(CODE_ANALYSIS, code_analysis_event.model_dump())
            logger.info("[Kafka] CodeAnalysisEvent published")
        except Exception as e:
            logger.error(f"[Kafka] Failed to publish CodeAnalysisEvent: {e}")
    return {"files_analyzed": len(results), "results": results}
