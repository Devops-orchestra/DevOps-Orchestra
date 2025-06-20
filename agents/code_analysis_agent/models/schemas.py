from pydantic import BaseModel
from typing import Optional

class LLMCodeAnalysisInput(BaseModel):
    repo: str
    branch: str
    commit_id: str
    repo_path: str
    file_limit: int = 5
    llm_model: Optional[str] = "llama-3.3-70b-versatile"