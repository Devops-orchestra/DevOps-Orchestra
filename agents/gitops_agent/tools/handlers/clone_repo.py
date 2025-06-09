import subprocess
import shutil
import os
from pydantic import BaseModel

class CloneRepoInput(BaseModel):
    repo_url: str
    branch: str = "main"
    clone_path: str

def run_clone_repo(data: dict):
    input_data = CloneRepoInput(**data)
    if os.path.exists(input_data.clone_path):
        shutil.rmtree(input_data.clone_path)
    subprocess.run([
        "git", "clone", "-b", input_data.branch,
        input_data.repo_url, input_data.clone_path
    ], check=True)
    return {"message": f"Cloned {input_data.repo_url} to {input_data.clone_path}"}