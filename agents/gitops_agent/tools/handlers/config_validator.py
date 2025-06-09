from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError
import yaml
import os

class ServiceEnv(BaseModel):
    key: str
    value: str

class DeploymentService(BaseModel):
    name: str
    runtime: str
    port: int
    env: List[ServiceEnv]

class Deployment(BaseModel):
    type: str
    provider: str
    strategy: str
    region: str
    services: List[DeploymentService]

class Project(BaseModel):
    name: str
    language: str
    framework: str
    repo: str

class Build(BaseModel):
    tool: str
    context: str
    dockerfile: str

class Testing(BaseModel):
    enabled: bool
    framework: str
    command: str

class Infrastructure(BaseModel):
    tool: str
    path: str

class Secrets(BaseModel):
    manager: str
    keys: List[str]

class RollbackThreshold(BaseModel):
    cpu: int
    errors: int
    duration: str

class Rollback(BaseModel):
    enabled: bool
    threshold: RollbackThreshold

class Alert(BaseModel):
    type: str
    threshold_ms: Optional[int] = None
    threshold: Optional[str] = None

class Observability(BaseModel):
    enabled: bool
    tools: List[str]
    alerts: List[Alert]

class ChatOps(BaseModel):
    enabled: bool
    platform: str
    channel: str
    notify_on: List[str]

class OrchestraConfig(BaseModel):
    project: Project
    build: Build
    testing: Testing
    deployment: Deployment
    infrastructure: Infrastructure
    secrets: Optional[Secrets]
    rollback: Optional[Rollback]
    observability: Optional[Observability]
    chatops: Optional[ChatOps]

def run_config_validation(data: dict):
    path = data.get("config_path")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"YAML config not found: {path}")
    with open(path, "r") as f:
        content = yaml.safe_load(f)
    try:
        validated = OrchestraConfig(**content)
        return {"message": "YAML config is valid.", "project": validated.project.name}
    except ValidationError as ve:
        raise Exception(f"Validation error: {ve}")
