import subprocess
from pydantic import BaseModel
import os
import sys

class LicenseAuditInput(BaseModel):
    repo_path: str

def run_license_audit(data: dict):
    input_data = LicenseAuditInput(**data)
    repo_path = input_data.repo_path

    requirements_path = os.path.join(repo_path, "requirements.txt")
    package_json_path = os.path.join(repo_path, "package.json")
    pom_xml_path = os.path.join(repo_path, "pom.xml")

    if os.path.exists(requirements_path):
        # Python: use piplicenses inside the project's venv
        result = subprocess.run(
            [sys.executable, "-m", "piplicenses", "--format=json"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    elif os.path.exists(package_json_path):
        # Node.js: use license-checker via npx
        result = subprocess.run(
            ["npx", "license-checker", "--json"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    elif os.path.exists(pom_xml_path):
        # Java/Maven: use maven license plugin (must be in the POM config)
        result = subprocess.run(
            ["mvn", "license:download-licenses"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
    else:
        raise Exception("No supported dependency manager found (requirements.txt, package.json, or pom.xml).")

    if result.returncode != 0:
        raise Exception(f"License audit failed: {result.stderr}")

    return {"licenses": result.stdout}
