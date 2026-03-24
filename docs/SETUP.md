# Setup

## Prerequisites

- **Python 3.10+** (see `Dockerfile` for container baseline)
- **Docker & Docker Compose** for the recommended stack (Kafka, coordinator app)
- **Slack workspace** with an app using Socket Mode (see [CONFIGURATION.md](CONFIGURATION.md))
- Optional: **Groq API key** for LLM-backed agents and failure suggestions; **Jira** credentials for test use-cases; **SonarCloud** or self-hosted **SonarQube** for code analysis

## Quick start (Docker)

1. Copy environment template and edit secrets:

   ```bash
   cp .env.example .env
   ```

2. Fill `SLACK_*`, `GROQ_API_KEY`, and other variables per [CONFIGURATION.md](CONFIGURATION.md).

3. Start the stack:

   ```bash
   docker compose up --build
   ```

4. Invite the Slack bot to your command channel and send a trigger (e.g. run pipeline for a branch). Pipeline logs go to the configured logs channel or webhook.

5. **GitOps tool server** (clone, `devops_orchestra.yaml` validation, license audit, repo size) is expected at `TOOL_SERVER_URL` (default `http://localhost:8001/invoke`). The coordinator can start it if configured—see `coordinator/main.py` and `agents/gitops_agent/main.py`.

## Local development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set KAFKA_BOOTSTRAP_SERVERS if Kafka runs elsewhere; run Zookeeper/Kafka or disable publishing.
python main.py
```

## Data directories

- Cloned repositories default under `REPO_BASE_PATH` (`/tmp/gitops_repos` in Docker, mounted from `./data/gitops_repos` in `docker-compose.yml`).

## Sonar

- **SonarCloud**: set `SONAR_HOST_URL=https://sonarcloud.io`, `SONAR_ORGANIZATION`, `SONAR_TOKEN`, `SONAR_PROJECT_KEY` in `.env`.
- **Self-hosted**: use `docker compose --profile self-hosted-sonar up -d` and point `SONAR_HOST_URL` at the SonarQube service.

See comments in `docker-compose.yml` and `.env.example`.
