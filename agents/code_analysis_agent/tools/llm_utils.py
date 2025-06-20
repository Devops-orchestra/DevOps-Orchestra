import re
from agents.code_analysis_agent.models.schemas import CodeAnalysisResult

def parse_llm_summary(text: str) -> CodeAnalysisResult:
    match = re.findall(r"(Errors|Warnings|Notes):\s*(\d+)", text)
    summary = {k.lower(): int(v) for k, v in match}

    return CodeAnalysisResult(
        passed=(summary.get("errors", 0) == 0),
        errors=["Error"] * summary.get("errors", 0),
        warnings=["Warning"] * summary.get("warnings", 0)
    )
