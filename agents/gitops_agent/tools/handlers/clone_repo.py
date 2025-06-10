import subprocess 
import shutil
import os
from pydantic import BaseModel

class CloneRepoInput(BaseModel):
    repo_url: str
    branch: str 
    clone_path: str

def run_clone_repo(data: dict):
    input_data = CloneRepoInput(**data)

    # --- Check 1: Git Installed ---
    if shutil.which("git") is None:
        raise Exception("Git is not installed or not found in PATH.")
   
    # --- Check 2: Repo URL Reachable --- 
    check_repo = subprocess.run(
        ["git", "ls-remote", input_data.repo_url],
        capture_output=True,
        text=True
    )
    
    if check_repo.returncode != 0:
        raise Exception(f"Cannot access repo URL:\nSTDOUT: {check_repo.stdout}\nSTDERR: {check_repo.stderr}")

    # --- Remove if existing ---
    if os.path.exists(input_data.clone_path):
        shutil.rmtree(input_data.clone_path)
   
    # --- Perform Clone ---
    result = subprocess.run(
        ["git", "clone", "-b", input_data.branch, input_data.repo_url, input_data.clone_path],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"Git clone failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    
    return {"message": f"Cloned {input_data.repo_url} to {input_data.clone_path}"}