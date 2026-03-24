# Features and recent additions

## Core

- **Multi-agent pipeline:** GitOps (clone, config validation, repo size, license audit), **repository indexing** (AST, optional Chroma), **SonarQube/SonarCloud** analysis, **Docker/build**, **LLM-generated tests** (with **Jira** use-case grounding when configured), **Terraform/IaC** plan, **deploy**, **rollback**.
- **`devops_orchestra.yaml`:** Per-repo config (build, test, deployment, infra, observability) validated by Pydantic in the GitOps tool server.
- **Kafka event bus:** Typed events (`event_schema.py`) and topics including `gitops_pipeline`, `code_analysis`, `build_ready`, `test_results`, `iac_ready`, `deployment_triggered`, `rollback_event`, etc.

## Coordinator & UX

- **Slack gateway** (Socket Mode): Triggers from user messages (and PR-style text); **pipeline logs** channel (or webhook) for step-by-step outcomes.
- **Failure handler:** Optional **Groq** LLM suggestions with **retry / skip / resolved** flows.
- **Skip semantics:** `PipelineSkips` + re-invocation so users can skip failed stages without forking the codebase manually.

## LangGraph

- **Full pipeline graph:** GitOps steps + index + analysis + build + test with conditional routing (e.g. skip code analysis when flagged).
- **Infra prepare graph:** IaC generation + plan (no apply).
- **Post-approval deploy graph:** Deploy with rollback edge (shared with `deployment_flow`).

## Quality & testing

- **Sonar** integration for static analysis; issues can be non-blocking with user **continue/stop** after Sonar.
- **Test agent retries** with **previous generated test code + pytest logs** fed back to the LLM for correction.

## Infrastructure

- **Docker Compose:** Zookeeper, Kafka, app; optional **SonarQube** profile.
- **Topic manager:** Creates Kafka topics on startup (including `gitops_pipeline`).
