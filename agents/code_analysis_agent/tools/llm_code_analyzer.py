import os
import glob
from jinja2 import Template
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.utils.logger import logger

SUPPORTED_EXTENSIONS = ["*.py", "*.js", "*.java", "*.cpp", "*.c", "*.html", "*.css", "*.ts"]

def read_prompt_template():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared_modules", "llm_config", "prompts", "code_analysis_prompt.txt")
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())

def analyze_code_with_llm(input_data: LLMCodeAnalysisInput):
    logger.info(f"Starting LLM code analysis for repo: {input_data.repo_path}")
    prompt_template = read_prompt_template()

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(glob.glob(os.path.join(input_data.repo_path, "**", ext), recursive=True))
    files = files[:input_data.file_limit]

    results = []
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
                model=input_data.llm_model,
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
    logger.info(f"LLM Results: {results}")
    return {"files_analyzed": len(results), "results": results}
