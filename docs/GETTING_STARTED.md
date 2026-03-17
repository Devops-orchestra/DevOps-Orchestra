# Getting Started — What You Need to Do

The pipeline is triggered from **Slack** (user messages or pull-request events). The old GitHub webhook (Flask + ngrok) entry point has been removed; the app runs only the **coordinator** daemon.

---

## Prerequisites

- **Python 3.10+** (recommended: use a virtual environment)
- **Slack workspace** (required)
- **Docker** (optional; only if you want to run the coordinator in Docker with Kafka for event publishing)

---

## 1. Install dependencies

```bash
cd /path/to/DevOps-Orchestra
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Set environment variables

Create a `.env` file in the project root (or export in your shell). **Required:**

| Variable | Required | Example |
|----------|----------|---------|
| `SLACK_BOT_TOKEN` | Yes | `xoxb-...` |
| `SLACK_APP_TOKEN` | Yes | `xapp-...` |
| `SLACK_COMMAND_CHANNEL_ID` | Yes | `C0AM13W4YKT` |
| `SLACK_PIPELINE_LOGS_CHANNEL_ID` | Yes* | `C0ALJPHBXS9` |
| `DEFAULT_REPO_URL` | Recommended | `https://github.com/org/repo.git` |

*Or use `SLACK_PIPELINE_LOGS_WEBHOOK_URL` instead of the channel ID.

**Optional (for full pipeline features):**

| Variable | Purpose |
|----------|---------|
| `JIRA_BASE_URL` | Test agent fetches use cases from Jira |
| `JIRA_API_TOKEN` | Jira API auth |
| `JIRA_EMAIL` | Jira API auth |
| `GROQ_API_KEY` | LLM suggestions on pipeline failures |
| `REPO_BASE_PATH` | Where to clone repos (default `/tmp/gitops_repos`) |
| `KAFKA_BOOTSTRAP_SERVERS` | Set to `disabled` to skip Kafka when not used |

See **docs/CONFIGURATION.md** for how to get Slack app tokens and channel IDs.

## 3. Run the coordinator

From the project root, either:

```bash
python main.py
```

or:

```bash
python -m coordinator.main
```

Both start the coordinator daemon. You do **not** need Kafka or a GitHub webhook URL.

What happens:

- Config is validated (Slack tokens and channel IDs).
- The **tool server** (clone, config validator) starts automatically on port **8001** if not already running.
- The daemon connects to Slack via **Socket Mode** and listens to the **command channel**.
- When you (or a PR event) trigger a run in that channel, the pipeline runs and logs go to the **pipeline logs channel**.

## 4. Run with Docker (optional)

To run the coordinator in Docker (e.g. with Kafka for event publishing):

```bash
docker-compose up --build
```

This starts Zookeeper, Kafka, and the **coordinator** (no Flask, no ngrok). Ensure your `.env` has the required Slack variables.

---

## Summary

| What to do | Command |
|------------|--------|
| Run locally (no Kafka) | `pip install -r requirements.txt`, set Slack env vars, then `python main.py` or `python -m coordinator.main` |
| Run in Docker | `docker-compose up --build` (starts Kafka + coordinator) |

Pipeline triggers: send **"Run pipeline for branch main"** (or branch name) in your Slack command channel.
