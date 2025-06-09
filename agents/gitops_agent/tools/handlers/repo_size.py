import os
from pydantic import BaseModel

class RepoSizeInput(BaseModel):
    repo_path: str

def run_repo_size(data: dict):
    input_data = RepoSizeInput(**data)
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(input_data.repo_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)

    size_mb = round(total_size / (1024 * 1024), 2)
    return {"repo_size_mb": size_mb}
