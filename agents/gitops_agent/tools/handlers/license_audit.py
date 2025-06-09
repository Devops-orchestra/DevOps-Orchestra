import subprocess
from pydantic import BaseModel
import os

class LicenseAuditInput(BaseModel):
    repo_path: str

def run_license_audit(data: dict):
    input_data = LicenseAuditInput(**data)
    venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    result = subprocess.run(
        [venv_python, "-m", "piplicenses", "--format=json"],
        cwd=input_data.repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"pip-licenses failed: {result.stderr}")
    return {"licenses": result.stdout}