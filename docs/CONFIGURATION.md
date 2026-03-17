# DevOps Orchestra — Configuration Guide

This guide walks you through configuring **Slack** (two channels, app, Socket Mode), **GitHub** (events into Slack), and **Jira** for the Coordinator daemon. The coordinator listens only to Slack; GitHub events are delivered to Slack via webhook/integration.

---

## 1. Slack Setup

### 1.1 Create a Slack App

1. Go to [Slack API — Your Apps](https://api.slack.com/apps).
2. Click **Create New App** → **From scratch**.
3. Name the app (e.g. `DevOps Orchestra`) and pick your workspace. Create the app.

### 1.2 Enable Socket Mode (no public URL)

1. In the app, open **Settings** → **Socket Mode**.
2. Turn **Socket Mode** **On**.
3. Create an **App-Level Token**:
   - Click **Generate** under "App-Level Tokens".
   - Name it (e.g. `socket-mode`) and add scope **`connections:write`**.
   - Generate and **copy the token** (starts with `xapp-`). This is your **`SLACK_APP_TOKEN`**.

### 1.3 Bot Token and Scopes

1. Open **OAuth & Permissions**.
2. Under **Scopes** → **Bot Token Scopes**, add:
   - **`chat:write`** — post messages in channels.
   - **`channels:history`** — read messages in public channels (needed for the command channel).
   - **`channels:read`** — list channel info (optional, for resolving channel names).
   - **`app_mentions:read`** — if you use @mentions (optional).
3. Install the app to your workspace (**Install to Workspace**). Copy the **Bot User OAuth Token** (starts with `xoxb-`). This is your **`SLACK_BOT_TOKEN`**.

### 1.4 Subscribe to message events (required for pipeline to trigger)

For the coordinator to see messages like "Run pipeline for branch main", Slack must send **message events** to your app:

1. In the Slack app, open **Event Subscriptions**.
2. Turn **Enable Events** **On**.
3. Under **Subscribe to bot events**, click **Add Bot User Event** and add **`message.channels`** (so the app receives messages in public channels it has joined).
4. If your command channel is **private**, also add **`message.groups`**.
5. **Reinstall the app** to your workspace if Slack prompts you.

Without `message.channels`, the app never receives your messages and the pipeline will not trigger.

### 1.5 Create Two Channels

1. **Command / trigger channel**  
   - Create a channel (e.g. `#devops-orchestra`) where:
     - Users send run requests (e.g. "Run pipeline for branch main").
     - GitHub events (push, pull request) will be posted (via GitHub → Slack integration).
   - Invite your Slack app to this channel: `/invite @DevOps Orchestra` (or your app name).

2. **Pipeline logs channel**  
   - Create a second channel (e.g. `#devops-pipeline-logs`) for:
     - Pipeline trigger, step results, errors, and completion.
   - Invite the same Slack app to this channel.

### 1.6 Get channel IDs

- **Method A (UI):** Right-click the channel name → **View channel details** → scroll to the bottom; the ID is there (e.g. `C01234ABCD`).
- **Method B (API):** In Slack, open the channel; the URL is `.../archives/C01234ABCD` — the last part is the channel ID.

Set:

- **`SLACK_COMMAND_CHANNEL_ID`** = ID of the command channel (e.g. `#devops-orchestra`).
- **`SLACK_PIPELINE_LOGS_CHANNEL_ID`** = ID of the pipeline logs channel (e.g. `#devops-pipeline-logs`).

**Optional:** If you prefer to post pipeline logs via an **Incoming Webhook** instead of the Bot token:
- Create an **Incoming Webhook** for the pipeline logs channel (Slack app → **Incoming Webhooks** → On → **Add New Webhook** → select the pipeline logs channel).
- Set **`SLACK_PIPELINE_LOGS_WEBHOOK_URL`** to that webhook URL. If set, the coordinator will use the webhook for pipeline logs instead of the Bot token (and you may omit `SLACK_PIPELINE_LOGS_CHANNEL_ID` for logs; command channel ID is still required).

### 1.7 Environment Variables (Slack)

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
export SLACK_COMMAND_CHANNEL_ID="C01234ABCD"      # Command/trigger channel
export SLACK_PIPELINE_LOGS_CHANNEL_ID="C05678EFGH" # Pipeline logs channel
# Optional: use webhook for pipeline logs instead of Bot
# export SLACK_PIPELINE_LOGS_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

---

## 2. GitHub → Slack (Events in Command Channel)

The coordinator does **not** expose an HTTP webhook for GitHub. GitHub events must appear in the **Slack command channel** so the daemon can see them. Only **pull_request** (and user messages) start the pipeline; push/commit are ignored.

### 2.1 Option A: GitHub for Slack (recommended)

1. In Slack, go to **Apps** → **Add apps** (or search "GitHub").
2. Install **GitHub** (official Slack app).
3. Connect your GitHub account/org and choose the repo(s).
4. **Subscribe to repository events** and select the channel = your **command channel** (e.g. `#devops-orchestra`).
5. Choose events to send to Slack; at minimum enable:
   - **Pull requests** (opened, closed, etc.) — required for PR-triggered runs.
   - Optionally **Pushes** (so you see them in Slack; the coordinator will still **not** start the pipeline on push).

Result: Pull request (and optionally push) notifications appear in the command channel. The coordinator treats **pull_request**-style bot messages as triggers; push messages are ignored for pipeline start.

### 2.2 Option B: GitHub Webhook → Slack via custom middleware

If you cannot use the GitHub for Slack app:

1. Create a small **middleware** that:
   - Receives GitHub webhook payloads (e.g. at `https://your-server/github-webhook`).
   - Filters for `pull_request` (and optionally `push`) events.
   - Posts a message to your **Slack command channel** (e.g. via Slack Incoming Webhook or Web API), including enough text so the coordinator’s trigger filter can detect a PR (e.g. "Pull request #42 opened" or similar).
2. In GitHub: **Settings** → **Webhooks** → **Add webhook**:
   - **Payload URL:** your middleware URL.
   - **Content type:** `application/json`.
   - **Secret:** optional but recommended.
   - **Events:** "Let me select individual events" → choose **Pull requests** (and optionally **Pushes**).
3. Ensure the middleware posts to the **same command channel** you set in `SLACK_COMMAND_CHANNEL_ID`.

The coordinator only starts the pipeline when it sees a **pull_request**-style message (or a user run request); push-only messages do not trigger the pipeline.

---

## 3. Jira Setup (Test Agent Use-Case Tool)

The Test agent uses Jira to fetch the use case (summary, description, acceptance criteria) for a ticket before generating tests. Configure Jira API access:

### 3.1 Create a Jira API Token

1. Log in to [Atlassian](https://id.atlassian.com).
2. Go to **Security** → **Create and manage API tokens**.
3. Create an API token and copy it. This is **`JIRA_API_TOKEN`**.

### 3.2 Jira Base URL and Email

- **Jira base URL:** Your Jira base URL, e.g. `https://your-domain.atlassian.net` (no trailing slash). Set **`JIRA_BASE_URL`**.
- **Email:** The Atlassian account email used for API access. Set **`JIRA_EMAIL`**.

### 3.3 Environment Variables (Jira)

```bash
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_API_TOKEN="your-api-token"
export JIRA_EMAIL="you@example.com"
```

These are used by the coordinator and by the Test agent’s Jira use-case tool. If the Jira ticket is unknown when the user requests a run, the coordinator will ask in the command channel and wait for the user’s reply.

---

## 4. Repo and Optional Settings

### 4.1 Default Repo and Path

```bash
export DEFAULT_REPO_URL="https://github.com/your-org/your-repo.git"
export REPO_BASE_PATH="/tmp/gitops_repos"   # optional; default clone path
```

### 4.2 Tool Server

The coordinator uses a **tool server** (clone, config validator) at `http://localhost:8001`. The daemon can start it automatically if not already running. To use a different URL:

```bash
export TOOL_SERVER_URL="http://localhost:8001/invoke"
```

### 4.3 LLM (Failure Suggestions)

For failure handling, the coordinator uses an LLM to suggest fixes. Set your API key (e.g. GROQ):

```bash
export GROQ_API_KEY="your-groq-api-key"
```

### 4.4 Kafka (if used elsewhere)

If other parts of the system use Kafka:

```bash
export KAFKA_BOOTSTRAP_SERVERS="kafka:9092"
```

---

## 5. Running the Coordinator

1. Install dependencies (includes `slack-bolt` and `slack-sdk`):
   ```bash
   pip install -r requirements.txt
   ```

2. Set all required environment variables (Slack, and optionally Jira, repo, GROQ, etc.).

3. From the project root, run the coordinator daemon:
   ```bash
   python -m coordinator.main
   ```

The daemon will:
- Validate Slack config (bot token, app token, command channel, and either pipeline logs channel ID or webhook URL).
- Optionally start the tool server on port 8001 if it’s not already running.
- Start the Slack gateway (Socket Mode) and listen to the **command channel**.
- On **user run request** or **pull_request** message: start the pipeline, post logs to the **pipeline logs channel**, and ask for user input (e.g. Jira ticket, retry/resolve) in the **command channel**.

---

## 6. Quick Reference — Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | App-Level Token for Socket Mode (`xapp-...`) |
| `SLACK_COMMAND_CHANNEL_ID` | Yes | Channel where users and GitHub events appear |
| `SLACK_PIPELINE_LOGS_CHANNEL_ID` | One of these | Channel for pipeline logs |
| `SLACK_PIPELINE_LOGS_WEBHOOK_URL` | One of these | Webhook URL for pipeline logs (alternative to channel ID) |
| `JIRA_BASE_URL` | If using Jira | Jira base URL (e.g. `https://your-domain.atlassian.net`) |
| `JIRA_API_TOKEN` | If using Jira | Jira API token |
| `JIRA_EMAIL` | If using Jira | Atlassian account email |
| `DEFAULT_REPO_URL` | Recommended | Default Git repo URL for clone |
| `REPO_BASE_PATH` | No | Local path for clones (default `/tmp/gitops_repos`) |
| `TOOL_SERVER_URL` | No | Tool server invoke URL (default `http://localhost:8001/invoke`) |
| `GROQ_API_KEY` | For failure suggestions | API key for LLM used in failure handling |
| `KAFKA_BOOTSTRAP_SERVERS` | If using Kafka | Kafka brokers (e.g. `kafka:9092`) |
| `SONAR_HOST_URL` | For code analysis | SonarCloud: `https://sonarcloud.io`; self-hosted: `http://sonarqube:9000` |
| `SONAR_TOKEN` | For code analysis | Token from SonarCloud or SonarQube (see [Sonar setup](SONAR_SETUP.md)) |
| `SONAR_ORGANIZATION` | For SonarCloud | Your SonarCloud organization key |
| `SONAR_PROJECT_KEY` | Optional | Override project key (default: `{repo}_{branch}`) |

---

## 7. Trigger Summary

| Source | In Slack | Pipeline starts? |
|--------|----------|------------------|
| User message (e.g. "Run pipeline for branch main") | Command channel | Yes |
| User message (e.g. "Run pipeline for PR #42") | Command channel | Yes |
| Pull request event (from GitHub app/webhook) | Command channel | Yes |
| Push / commit event | Command channel | No (ignored) |

Pipeline logs (trigger, steps, errors, completion) always go to the **pipeline logs channel**; user questions (Jira ticket, retry/resolve) stay in the **command channel**.
