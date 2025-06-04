"""
topics.py

Defines the Kafka topic names used across the DevOps orchestration pipeline.

Each constant represents a unique event type emitted or consumed by system agents,
enabling event-driven communication between microservices such as GitOps, Build,
Test, IaC, Deployment, and Observability agents.

Constants:
    CODE_PUSH: Triggered when a new code commit is pushed to the repository.
    CODE_ANALYSIS: Triggered after static code analysis completes.
    TEST_RESULTS: Triggered after test execution (unit, integration, etc.).
    BUILD_READY: Emitted when a build is complete (successful or failed).
    IAC_READY: Indicates that infrastructure provisioning is done.
    DEPLOYMENT_TRIGGERED: Signifies a deployment has been started or completed.
    OBSERVABILITY_ALERT: Alert based on monitoring/metrics anomalies.
    ROLLBACK_EVENT: Issued when a rollback is initiated due to failures.
"""

CODE_PUSH = "code_push"
CODE_ANALYSIS = "code_analysis"
TEST_RESULTS = "test_results"
BUILD_READY = "build_ready"
IAC_READY = "iac_ready"
DEPLOYMENT_TRIGGERED = "deployment_triggered"
OBSERVABILITY_ALERT = "observability_alert"
ROLLBACK_EVENT = "rollback_event"