"""
devops_state.py

Defines the shared state object `DevOpsAgentState` used by all agents in the
DevOps Orchestra. This state is passed and updated across agents via Kafka
and LangGraph. Each agent can update only its own slice of this state.
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Dict, List


class StatusEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"


class SeverityEnum(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RepoContext(BaseModel):
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    config: Optional[dict] = None
    size_mb: Optional[float] = None


class CodeAnalysisResult(BaseModel):
    passed: bool = False
    warnings: List[str] = []
    errors: List[str] = []
    logs: List[str] = []


class TestResults(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    coverage: float = 0.0
    status: StatusEnum = StatusEnum.NOT_STARTED
    retries: int = 0 
    logs: List[str] = []


class BuildResult(BaseModel):
    image_url: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: Optional[str] = None
    retries: int = 0 


class InfraState(BaseModel):
    resources: Optional[Dict[str, str]] = None
    outputs: Optional[Dict[str, str]] = None
    status: StatusEnum = StatusEnum.NOT_STARTED


class DeploymentState(BaseModel):
    environment: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: Optional[str] = None


class ObservabilityState(BaseModel):
    alerts: List[str] = []
    metrics_url: Optional[str] = None
    rollback_triggered: bool = False


class ChatOpsCommand(BaseModel):
    user: str
    command: str
    timestamp: str


class DevOpsAgentState(BaseModel):
    repo_context: RepoContext = Field(default_factory=RepoContext)
    code_analysis: CodeAnalysisResult = Field(default_factory=CodeAnalysisResult)
    test_results: TestResults = Field(default_factory=TestResults)
    build_result: BuildResult = Field(default_factory=BuildResult)
    infra: InfraState = Field(default_factory=InfraState)
    deployment: DeploymentState = Field(default_factory=DeploymentState)
    observability: ObservabilityState = Field(default_factory=ObservabilityState)
    chatops_command: Optional[ChatOpsCommand] = None
    agent_logs: List[str] = []
    current_agent: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    last_event: Optional[Dict] = None
    llm_context_memory: Optional[str] = None 
