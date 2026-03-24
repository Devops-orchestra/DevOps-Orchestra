"""Audit dependency manifests for license metadata (pip, npm, maven).
Implements the license_audit tool for the GitOps stage of the pipeline.
"""
import os
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel


class LicenseAuditInput(BaseModel):
    repo_path: str


# Directories to skip when searching for dependency files (reduces noise)
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "env", ".env", "dist", "build"}


def _find_dependency_files(repo_path: str):
    """Find all requirements.txt, package.json, and pom.xml under repo_path (including subfolders)."""
    requirements = []
    package_jsons = []
    pom_xmls = []
    repo = Path(repo_path)
    if not repo.is_dir():
        return requirements, package_jsons, pom_xmls
    for root, dirs, files in os.walk(repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        root_path = Path(root)
        if "requirements.txt" in files:
            requirements.append(root_path / "requirements.txt")
        if "package.json" in files:
            package_jsons.append(root_path / "package.json")
        if "pom.xml" in files:
            pom_xmls.append(root_path / "pom.xml")
    print("requirements, package_jsons, pom_xmls: ", requirements, package_jsons, pom_xmls)
    return requirements, package_jsons, pom_xmls


def run_license_audit(data: dict):
    input_data = LicenseAuditInput(**data)
    repo_path = input_data.repo_path

    requirements, package_jsons, pom_xmls = _find_dependency_files(repo_path)
    all_licenses = []
    last_error = None

    for req_path in requirements:
        cwd = str(req_path.parent)
        result = subprocess.run(
            ["pip-licenses", "--format=json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            all_licenses.append({"path": str(req_path), "type": "python", "output": result.stdout})
        else:
            last_error = result.stderr or result.stdout

    for pkg_path in package_jsons:
        cwd = str(pkg_path.parent)
        result = subprocess.run(
            ["npx", "--yes", "license-checker", "--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            all_licenses.append({"path": str(pkg_path), "type": "node", "output": result.stdout})
        else:
            last_error = result.stderr or result.stdout

    for pom_path in pom_xmls:
        cwd = str(pom_path.parent)
        result = subprocess.run(
            ["mvn", "license:download-licenses"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            all_licenses.append({"path": str(pom_path), "type": "maven", "output": result.stdout})
        else:
            last_error = result.stderr or result.stdout

    if not all_licenses and not (requirements or package_jsons or pom_xmls):
        raise Exception("No supported dependency manager found (requirements.txt, package.json, or pom.xml) in repo or subfolders.")

    if not all_licenses:
        raise Exception(f"License audit failed for all found files: {last_error or 'unknown'}")
    print("all_licenses: ", all_licenses)
    return {"licenses": all_licenses}
