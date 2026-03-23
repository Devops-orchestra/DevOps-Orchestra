"""
devops_state.py

Defines the shared state object `DevOpsAgentState` used by all agents in the
DevOps Orchestra. This state is passed and updated across agents via Kafka
and LangGraph. Each agent can update only its own slice of this state.
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Dict, List, Any


class StatusEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"


class SeverityEnum(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PipelineMeta(BaseModel):
    """One pipeline run (Slack / GitHub / etc.)."""

    pipeline_id: str = ""
    trigger_type: str = "unknown"  # slack | github | manual | ...
    status: StatusEnum = StatusEnum.NOT_STARTED


class GitMetadata(BaseModel):
    """Git facts after clone; diff vs main/master for incremental context."""

    local_path: Optional[str] = None
    branch: Optional[str] = None
    base_ref_used: Optional[str] = None
    changed_files: List[str] = Field(default_factory=list)
    diff_summary: Optional[str] = None


class IndexArtifacts(BaseModel):
    """Structured repo index (AST, call hints, optional vector store)."""

    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: List[str] = Field(default_factory=list)
    index_root: Optional[str] = None
    ast_map_path: Optional[str] = None
    call_graph_path: Optional[str] = None
    vector_store_path: Optional[str] = None
    retrieval_context_path: Optional[str] = None
    symbol_count: int = 0
    file_count: int = 0
    embedding_backend: Optional[str] = None  # chromadb | none


class SonarReport(BaseModel):
    """Structured Sonar output (parallel to human-readable code_analysis lists)."""

    project_key: Optional[str] = None
    host_url: Optional[str] = None
    issues_raw: List[Dict[str, Any]] = Field(default_factory=list)
    severity_counts: Dict[str, int] = Field(default_factory=dict)


class RepoContext(BaseModel):
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    config: Optional[dict] = None
    size_mb: Optional[float] = None


class CodeAnalysisResult(BaseModel):
    passed: bool = False
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    sonar: SonarReport = Field(default_factory=SonarReport)


class TestResults(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    coverage: float = 0.0
    status: StatusEnum = StatusEnum.NOT_STARTED
    retries: int = 0
    logs: List[str] = Field(default_factory=list)
    # Last failed autogen attempt (fed back to LLM on retry)
    last_generated_code: Optional[str] = None
    last_run_failure_logs: Optional[str] = None


class BuildResult(BaseModel):
    image_url: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: Optional[str] = None
    retries: int = 0


class InfraState(BaseModel):
    resources: Optional[Dict[str, str]] = None
    outputs: Optional[Dict[str, str]] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: Optional[str] = None
    # Plan approved by user; deployment agent applies (no apply in infra agent).
    plan_accepted: bool = False
    infra_path: Optional[str] = None
    infra_tool: Optional[str] = None


class DeploymentState(BaseModel):
    environment: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    logs: Optional[str] = None


class ObservabilityState(BaseModel):
    alerts: List[str] = Field(default_factory=list)
    metrics_url: Optional[str] = None
    rollback_triggered: bool = False


class ChatOpsCommand(BaseModel):
    user: str
    command: str
    timestamp: str


class DevOpsAgentState(BaseModel):
    pipeline: PipelineMeta = Field(default_factory=PipelineMeta)
    git_meta: GitMetadata = Field(default_factory=GitMetadata)
    index: IndexArtifacts = Field(default_factory=IndexArtifacts)
    repo_context: RepoContext = Field(default_factory=RepoContext)
    code_analysis: CodeAnalysisResult = Field(default_factory=CodeAnalysisResult)
    test_results: TestResults = Field(default_factory=TestResults)
    build_result: BuildResult = Field(default_factory=BuildResult)
    infra: InfraState = Field(default_factory=InfraState)
    deployment: DeploymentState = Field(default_factory=DeploymentState)
    observability: ObservabilityState = Field(default_factory=ObservabilityState)
    chatops_command: Optional[ChatOpsCommand] = None
    agent_logs: List[str] = Field(default_factory=list)
    current_agent: Optional[str] = None
    status: StatusEnum = StatusEnum.NOT_STARTED
    last_event: Optional[Dict] = None
    llm_context_memory: Optional[str] = None
