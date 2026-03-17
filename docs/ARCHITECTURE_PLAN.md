# DevOps Orchestra — Upgraded Architecture Plan

## 1. Current System Context (Summary)

The existing system is an event-driven, multi-agent DevOps platform:

- **Entry:** Flask webhook receives GitHub events; GitOps agent runs (clone, validate `devops_orchestra.yaml`, license audit, repo size), then publishes `CODE_PUSH` to Kafka.
- **Orchestration:** LangGraph combined flow consumes `CODE_PUSH` and runs: code analysis → build → test → provision infra → deploy → rollback (with conditional edges and failure notifications).
- **State:** Shared `DevOpsAgentState` (repo_context, code_analysis, test_results, build_result, infra, deployment, etc.) passed through the pipeline.
- **Agents:** GitOps, Code Analysis, Build, Test, Infrastructure, Deployment, Rollback, Slack (notifications). Test agent today generates tests via LLM from code context; no Jira use-case tool.
- **Communication:** Kafka for events; Slack for failure notifications (one webhook); GitHub webhook for triggers.

This plan describes the **upgraded** architecture: Coordinator daemon with gateway, Slack as the single entry point (user messages + GitHub events via webhook), **only user messages and pull-request events** as triggers (no push/commit validation), full pipeline, Test agent with a **Jira use-case tool**, **separate Slack channel for all pipeline logs**, user input via Slack, and on failure: ask user to retry or resolve with LLM suggested fix each time via Slack.

---

## 2. Upgraded Architecture Overview

### 2.1 Coordinator Daemon and Gateway

- **Coordinator** runs as a **background daemon** (long-lived process).
- It has a **gateway layer** that is the single entry point for all incoming signals.
- The **gateway** listens for messages from **Slack** only (no direct HTTP webhook for GitHub to the app; GitHub is configured to send events into Slack via webhook/integration, so the coordinator sees GitHub activity as messages in Slack).

### 2.2 Slack Channels (Two Channels)

- **Channel 1 — Command / trigger channel:**  
  Users send messages here. GitHub events (push, pull requests) are also received in this channel via **webhook configured in GitHub** (e.g. GitHub Slack app or webhook that posts to this channel).  
  The daemon looks for **user messages** or **pull-request events** in this channel to start the pipeline.

- **Channel 2 — Pipeline logs channel (separate):**  
  All pipeline-related logs, errors, and results are sent to this **separate** Slack channel. Pipeline trigger, each step’s outcome, and pipeline completion are all logged here. User prompts (e.g. “provide Jira ticket”) and failure/recovery prompts stay in the command channel (or can be mirrored to logs channel as per product choice).

### 2.3 Triggers (What Starts the Pipeline)

- **Valid triggers:**
  - A **user message** in the command channel (e.g. “Run pipeline for branch X” or “Run pipeline for PR #42”).
  - A **pull request** event from GitHub that appears in the command channel (via the GitHub webhook configured to post there).
- **Not triggers:**  
  **Commit events and push events are not validated/triggered.** The pipeline does not start on every push or commit; only on explicit user request or on pull-request events received in Slack.

### 2.4 Pipeline (Agents Sequence)

When a trigger is detected, the **agents pipeline** runs in order:

1. **Clone** the specific branch (from user message or from the PR’s branch).
2. **Validate** `devops_orchestra.yaml` (schema and required fields).
3. **Code analysis agent** — static/code quality analysis (LLM-based).
4. **Test case generation and validation** — Test agent uses the **appropriate use case from Jira** (via a **Jira use-case tool**), generates test cases through the LLM for the code, then runs and validates tests.
5. **Build agent** — build application (Docker/Maven/npm/etc. per config).
6. **Infrastructure creation** — provision infra (e.g. Terraform).
7. **Deployment pipeline agent** — deploy application.
8. **Rollback agent** — used if deployment (or a critical step) fails.

All errors and results from each step are **logged and sent to the separate Slack channel** (pipeline logs channel). Pipeline trigger and completion are also sent to that channel.

### 2.5 Test Agent and Jira Use Case

- The **Test agent** must take the **appropriate use case from Jira** for the code and generate test cases through the LLM.
- The Test agent **must have a tool that gets the use case from Jira** (e.g. given a Jira ticket key, call Jira API and return summary, description, acceptance criteria). This tool is used before generating tests so the LLM prompt is grounded in the Jira use case.
- If the **Jira use case number (ticket key) is unknown**, the coordinator **asks the user through Slack** (in the command channel) and waits for the user’s reply before continuing. Any other input needed from the user is **requested through Slack** in the same way.

### 2.6 User Input via Slack

- Any input required from the user (e.g. Jira ticket key, branch name, confirmation) is **requested through Slack** (command channel). The coordinator posts the question and **waits for the user’s reply** in that channel (or thread) before proceeding.
- This includes: Jira use case number when unknown, and any retry/resolve decisions after a failure (see below).

### 2.7 Failure Handling: Retry or Resolve with LLM (Each Time via Slack)

- If **any agent fails** in the pipeline (e.g. build agent fails, test agent fails), the **coordinator does not auto-retry indefinitely**. Instead:
  - The failure and relevant logs/errors are sent to the **pipeline logs channel**.
  - The coordinator **asks the user through Slack** (command channel) to **retry or resolve the errors**. Each time an agent fails, the coordinator **uses an LLM** to analyze the error and suggest a resolution (e.g. suggested fix, or “retry after fixing X”). This **LLM suggestion is sent to the user through Slack** along with the question (e.g. “Build failed. Suggested fix: … Do you want to retry or resolve and try again?”). The user can then reply (e.g. “retry” or “fixed, run again”) and the coordinator proceeds accordingly (retry the step or re-run from the failed step).
- So: **each time** an agent fails, the coordinator (1) logs to the pipeline logs channel, (2) asks the user via Slack to retry or resolve, and (3) **consults the LLM each time** and sends that suggestion through Slack to the user.

---

## 3. Component Design (Upgraded)

### 3.1 Coordinator (Background Daemon)

- **Role:** Long-running process that runs the **gateway layer** and orchestrates the pipeline.
- **Startup:** Bootstrap Kafka (wait, create topics), load config (Slack tokens, Jira API, repo URL, **two Slack channel IDs**: command channel, pipeline-logs channel), then start the gateway and block.
- **No Flask webhook for GitHub:** GitHub events (push, PR) are received **in Slack** via webhook/integration configured in GitHub; the coordinator only reads from Slack.
- **State:** One run state (e.g. `DevOpsAgentState`) per pipeline run, keyed by correlation ID or channel + message_ts so concurrent runs do not overwrite each other.

### 3.2 Gateway Layer

- **Role:** Single entry point for all incoming signals. Listens only to **Slack** (command channel).
- **Inputs:**  
  - **User messages** in the command channel.  
  - **GitHub events** that appear in the command channel (push, pull request) — from webhook configured in GitHub to post to that channel.
- **Trigger logic:**  
  - **User message** → parse intent (e.g. “run pipeline for branch X” or “run pipeline for PR #42”); if it is a pipeline run request, start the pipeline.  
  - **GitHub event** → only **pull_request** events start the pipeline. **Push and commit events are not validated/triggered** (ignored for pipeline start).
- **Outputs:**  
  - Post user prompts and questions to the **command channel** (e.g. “Please provide Jira ticket number”, “Build failed. LLM suggestion: … Retry or resolve?”).  
  - Send **all pipeline logs, errors, and results** to the **separate pipeline logs channel**.

### 3.3 Two Slack Channels

| Channel | Purpose |
|--------|---------|
| **Command / trigger channel** | User messages; GitHub events (push, PR) posted here via webhook. Triggers (user run request, PR event) are detected here. All questions to the user (Jira ticket, retry/resolve) are posted here. |
| **Pipeline logs channel** | All logs from pipeline trigger, each step’s result, errors, and pipeline completion. No user interaction; read-only stream of pipeline activity. |

### 3.4 Pipeline Sequence (Detailed)

1. **Resolve branch/repo:** From user message (e.g. branch name, PR number) or from PR event (branch and repo from payload).
2. **Clone** that branch to a local path.
3. **Validate** `devops_orchestra.yaml` in the repo; on failure log to pipeline logs channel and either stop or ask user (in command channel) to fix.
4. **Code analysis agent** — run; post result and errors to **pipeline logs channel**. On failure → ask user via Slack (command channel) to retry or resolve; LLM suggestion each time via Slack.
5. **Test agent:**  
   - **Jira use case:** Use the **Test agent’s Jira tool** to get the use case (summary, acceptance criteria) for the ticket. If ticket key unknown → ask user in **command channel**, wait for reply, then fetch use case.  
   - Generate test cases via LLM from that use case and code; run tests; post results/errors to **pipeline logs channel**. On failure → ask user to retry or resolve with LLM suggestion via Slack.
6. **Build agent** — run; post result/errors to **pipeline logs channel**. On failure → ask user to retry or resolve with LLM suggestion via Slack.
7. **Infrastructure creation** — run; post result/errors to **pipeline logs channel**. On failure → ask user to retry or resolve with LLM suggestion via Slack.
8. **Deployment pipeline agent** — run; post result/errors to **pipeline logs channel**. On failure → trigger rollback and ask user to retry or resolve with LLM suggestion via Slack.
9. **Rollback agent** — run if needed; post result to **pipeline logs channel**.

Pipeline **trigger** and **completion** (success or failure) messages are sent to the **pipeline logs channel**.

### 3.5 Test Agent: Jira Use-Case Tool

- The Test agent **must expose or use a tool** that **gets the use case from Jira** (e.g. `get_jira_use_case(ticket_key: str) -> UseCase`). That tool should:
  - Call Jira API (e.g. GET issue by key).
  - Return summary, description, acceptance criteria (or similar) so the LLM can generate test cases aligned with the use case.
- This tool is used **before** generating test cases. If the ticket key is missing, the coordinator asks the user in the command channel and, after reply, passes the key to the Test agent so it can call this tool.

### 3.6 Failure Flow (Retry or Resolve with LLM, via Slack)

- When any agent fails:
  1. Coordinator sends failure details and relevant logs to the **pipeline logs channel**.
  2. Coordinator calls an **LLM** with the error context and gets a **suggested resolution** (e.g. “Fix the Dockerfile base image and retry”, or “Retry after ensuring port 5000 is free”).
  3. Coordinator posts in the **command channel** a message to the user: e.g. “Agent X failed. Suggested fix (LLM): … Do you want to **retry** or **resolve and run again**?” and waits for the user’s reply.
  4. On **retry** → re-run the failed step (or from that step onward). On **resolve and run again** → user indicates they fixed the issue; coordinator re-runs from the failed step or from the beginning as designed.
- This behavior is applied **each time** an agent fails; the LLM is consulted each time and the suggestion is sent through Slack.

---

## 4. Configuration

- **Slack:**  
  - Bot token (and app token if using Socket Mode) for the coordinator app.  
  - **Command channel ID** (where users and GitHub events appear).  
  - **Pipeline logs channel ID** (where all pipeline logs, errors, and results are sent).  
  - Optional: webhook URL for the pipeline logs channel if posting via webhook instead of API.
- **GitHub:**  
  - Configure **webhook** (or Slack integration) so that **push** and **pull_request** events are sent to the **Slack command channel** (so the daemon sees them). The daemon will only **validate/trigger** on **pull_request** (and user messages); push/commit do not trigger.
- **Jira:**  
  - Base URL, API token (or equivalent), and any auth needed for the Test agent’s **get use case from Jira** tool.
- **Repo:**  
  - Default repo URL and branch naming convention as needed for clone and PR resolution.

---

## 5. Suggested Directory Layout

```text
coordinator/
  __init__.py
  main.py                      # Daemon entry: Kafka, gateway, run loop
  gateway/
    __init__.py
    slack_gateway.py           # Listen to Slack (command channel); classify user vs GitHub
    trigger_filter.py         # Only user run-request and pull_request; ignore push/commit
    intent_parser.py          # Parse user message → branch/PR, optional Jira key
  handlers/
    __init__.py
    pipeline_handler.py       # Run full pipeline; post logs to pipeline logs channel
    failure_handler.py        # On agent failure: LLM suggestion, ask user retry/resolve via Slack
  slack_logger.py             # Send pipeline logs/errors/results to separate pipeline logs channel

agents/
  test_agent/
    tools/
      jira_use_case_tool.py   # Tool: get use case from Jira (summary, acceptance criteria)
      llm_test_generator.py  # Generate tests from Jira use case + code via LLM
  ...
```

---

## 6. Implementation Checklist

- [ ] **Coordinator daemon** — `coordinator/main.py`: start gateway, no Flask; only Slack.
- [ ] **Gateway layer** — Listen to **command channel**; receive user messages and GitHub events (via webhook configured in GitHub to that channel).
- [ ] **Trigger filter** — Pipeline starts only on **user run request** or **pull_request** event; **push and commit events are not validated/triggered**.
- [ ] **Two Slack channels** — Command channel (triggers + user questions); **separate pipeline logs channel** (all pipeline logs, errors, results, trigger and completion).
- [ ] **Pipeline handler** — Full sequence: clone → validate yaml → code analysis → test (Jira use case + LLM) → build → infra → deploy → rollback; send all logs/errors/results to **pipeline logs channel**.
- [ ] **Test agent: Jira use-case tool** — Implement `get_jira_use_case(ticket_key)` (or equivalent) and use it before generating tests. If ticket unknown, coordinator asks user in command channel.
- [ ] **User input via Slack** — Any missing input (e.g. Jira ticket) requested in command channel; wait for user reply.
- [ ] **Failure handling** — On any agent failure: log to pipeline logs channel; call LLM for resolution suggestion; ask user in command channel to retry or resolve; send LLM suggestion through Slack; proceed on user reply (retry or re-run).
- [ ] **Config** — Command channel ID, pipeline logs channel ID, Jira API, repo URL, GitHub webhook configured to post to command channel.

---

## 7. Summary Table

| Item | Description |
|------|-------------|
| **Coordinator** | Background daemon with gateway layer; listens only to Slack. |
| **Gateway** | Listens to command channel for user messages and GitHub events (webhook configured in GitHub to that channel). |
| **Triggers** | User message (run pipeline) or **pull_request** event. **Push and commit are not validated/triggered.** |
| **Pipeline** | Clone → validate devops_orchestra.yaml → code analysis → test (Jira use case + LLM) → build → infra → deploy → rollback. |
| **Test agent** | Has a **tool that gets use case from Jira**; generates test cases via LLM from that use case and code. |
| **Slack channels** | **Command channel:** triggers + user questions. **Separate pipeline logs channel:** all logs, errors, results, trigger and completion. |
| **User input** | Jira ticket (if unknown) and any other input requested through Slack (command channel). |
| **On agent failure** | Log to pipeline logs channel; ask user via Slack to retry or resolve; **LLM asked each time** and suggestion sent through Slack; proceed on user reply. |
