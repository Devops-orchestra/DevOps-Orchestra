# Future scope

Non-exhaustive roadmap ideas; priorities depend on product needs.

## Orchestration

- **LangGraph checkpoints / interrupts** to pause the graph at plan approval instead of coordinator glue between two graphs.
- **Single invoke** for infra + deploy once human approval is modeled as a first-class graph interrupt.
- **Dynamic topic subscriptions** per tenant or per repo.

## Agents & integrations

- Deeper **GitHub App** integration (optional) alongside Slack-first triggers.
- **Observability agent** wired continuously post-deploy with dashboards and SLO-based rollback.
- **Policy-as-code** gates (OPA, security scanners) as explicit graph nodes.

## Platform

- **Multi-tenant** workspace isolation, secrets backends, and audit logs.
- **UI** (web) for pipeline history beyond Slack threads.
- **Metrics** export (Prometheus/OpenTelemetry) from coordinator and agents.

## Developer experience

- **Contract tests** for Kafka schemas and `DevOpsAgentState` versioning.
- **E2E** tests against docker-compose with mocked Sonar/Slack.

Contributions should keep **state** and **events** consistent: treat `DevOpsAgentState` as canonical and Kafka as the broadcast layer for cross-service observers.
