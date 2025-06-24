"""
event_schema.py

Defines the event schemas used in the DevOps orchestration pipeline.

Each event class represents a message structure for a specific type of interaction 
between agents in the system, such as code push notifications, test results, build 
completion, infrastructure readiness, deployment status, observability alerts, and 
rollbacks.

These schemas are built using Pydantic models and help enforce validation and 
consistency for messages exchanged over Kafka.

Modules:
- StatusEnum: Standardized status values for task outcomes.
- SeverityEnum: Levels of alert severity for observability.
- CodePushEvent: Emitted when code is pushed to a repository.
- CodeAnalysisEvent: Emitted after static code analysis is completed.
- TestResultsEvent: Emitted after test execution with validations.
- BuildReadyEvent: Emitted upon successful or failed Docker builds.
- IaCReadyEvent: Emitted after infrastructure provisioning.
- DeploymentEvent: Emitted during or after deployment operations.
- ObservabilityAlertEvent: Emitted when monitoring detects an issue.
- RollbackEvent: Emitted when a service is rolled back due to failure.

Usage:
    These event schemas are used for validating and serializing/deserializing messages 
    sent to and from Kafka topics in the DevOps orchestration system.

Author:
    Raahul Krishna 
"""

from pydantic import BaseModel, model_validator
from typing import Optional, Dict, Any, List
from enum import Enum


# -------- Enums -------- #

class StatusEnum(str, Enum):
    """Defines standard statuses for build, infra, deployment stages."""
    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


class SeverityEnum(str, Enum):
    """Defines alert severity levels used in observability events."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# -------- Event Schemas -------- #

class CodePushEvent(BaseModel):
    """
    Emitted by GitOps Agent when a new code push event is detected.
    """
    repo: str                          # GitHub repo name
    branch: str                        # Target branch
    commit_id: str                     # Commit hash
    code: str                          # Optional code snapshot or metadata
    config: Optional[Dict[str, Any]]   # Parsed devops_orchestra.yaml contents


class CodeAnalysisEvent(BaseModel):
    """
    Emitted after static code analysis is performed by the Code Analysis Agent.
    """
    repo: str                          # Repo under analysis
    passed: bool                       # Overall pass/fail status
    warnings: List[str]                # List of warnings
    errors: List[str]                  # List of errors
    notes: List[str]                   # List of notes
    agent: str = "code_analysis_agent" # Originating agent


class TestResultsEvent(BaseModel):
    """
    Emitted by the Testing Agent after running generated or pre-defined tests.
    """
    repo: str
    total_tests: int                   # Total number of tests run
    passed: int                        # Number of tests passed
    failed: int                        # Number of tests failed
    coverage: Optional[float]         # Optional code coverage (0–100)
    logs: Optional[str]               # Raw test logs or stdout/stderr
    agent: str = "testing_agent"

    @model_validator(mode="after")
    def validate_totals(self) -> "TestResultsEvent":
        """
        Validates that passed + failed equals total_tests.
        """
        if self.passed + self.failed != self.total_tests:
            raise ValueError("passed + failed must equal total_tests")
        return self


class BuildReadyEvent(BaseModel):
    """
    Emitted by the Build Agent after attempting to build a Docker image.
    """
    repo: str
    image_url: str                     # URL of the built Docker image
    status: StatusEnum                # "success" or "failed"
    logs: Optional[str]               # Build logs
    agent: str = "build_agent"


class IaCReadyEvent(BaseModel):
    """
    Emitted by the IaC Agent after infrastructure is provisioned or failed.
    """
    repo: str
    resources: List[str]              # List of provisioned resources (e.g., ["EC2", "S3"])
    status: StatusEnum
    logs: Optional[str]               # Terraform logs or summary
    outputs: Optional[Dict[str, str]] # Terraform output variables
    agent: str = "iac_agent"


class DeploymentEvent(BaseModel):
    """
    Emitted by the Deployment Agent to indicate deployment progress or completion.
    """
    repo: str
    service_name: str                 # Name of the service deployed
    version: str                      # Version or tag deployed
    strategy: str                     # Deployment strategy (e.g., blue-green, canary)
    status: StatusEnum
    logs: Optional[str]               # Deployment logs
    agent: str = "deployment_agent"


class ObservabilityAlertEvent(BaseModel):
    """
    Emitted by the Observability Agent when an alert is triggered.
    """
    repo: str
    service: str                      # Affected service name
    issue: str                        # Brief description of the issue
    severity: SeverityEnum            # Severity level of the alert
    logs: Optional[str]               # Log or error messages
    metrics: Optional[Dict[str, Any]] # Relevant metrics (e.g., CPU, memory)
    agent: str = "observability_agent"


class RollbackEvent(BaseModel):
    """
    Emitted when a rollback is triggered, either manually or automatically.
    """
    repo: str
    service: str                      # Rolled-back service
    reason: str                       # Reason for rollback (e.g., crash, bad deploy)
    triggered_by: str                 # Who or what triggered it (e.g., agent or user)
    logs: Optional[str]               # Logs or rollback messages
    rollback_to: Optional[str]        # Target version/hash to rollback to
    agent: str = "deployment_agent"
