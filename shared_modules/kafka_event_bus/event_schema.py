from pydantic import BaseModel

class CodePushEvent(BaseModel):
    repo: str
    branch: str
    commit_id: str

class BuildReadyEvent(BaseModel):
    image_url: str
    status: str

class DeploymentEvent(BaseModel):
    service_name: str
    version: str
    strategy: str
