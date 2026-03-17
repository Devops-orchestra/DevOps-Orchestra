# Code analysis: SonarCloud (free cloud) setup

The code analysis agent can use **SonarCloud** (free for public repos) so you don't run or maintain a SonarQube server. One-time setup below; then add the token to `.env` and run the app.

---

## 1. Create a SonarCloud account and organization

1. Go to [https://sonarcloud.io](https://sonarcloud.io) and sign in with **GitHub**, **GitLab**, or **Bitbucket**.
2. Create an **organization** (e.g. `my-org`). This is your `SONAR_ORGANIZATION` key.

---

## 2. Add a project and get the token

1. In SonarCloud, click **Add new project** and choose the repository you want to analyze (e.g. your DevOps-Orchestra repo or the repo the pipeline will clone).
2. Confirm the **project key** (e.g. `my-org_devops-orchestra`). You’ll use this as `SONAR_PROJECT_KEY` if it differs from the default `{repo}_{branch}`.
3. Go to the project → **Administration** → **Analysis Method** (or **Project Settings**).
4. Under **Analyze new code**, create or copy a **token** (e.g. "DevOps Orchestra"). This is your **`SONAR_TOKEN`**.

---

## 3. Configure the app

Add to your **`.env`** (do not commit the token):

```env
# SonarCloud (free cloud – no server to run)
SONAR_HOST_URL=https://sonarcloud.io
SONAR_ORGANIZATION=my-org
SONAR_TOKEN=your-sonarcloud-token-here
# Optional: only if your project key is not "{repo}_{branch}"
# SONAR_PROJECT_KEY=my-org_my-repo
```

Start the stack **without** the self-hosted SonarQube container:

```bash
docker-compose up -d
```

The code analysis step will run `sonar-scanner` against the cloned repo and send results to SonarCloud; issues are summarized and shown in the pipeline logs and in Slack.

---

## 4. Self-hosted SonarQube (optional)

If you prefer to run SonarQube yourself (e.g. in Docker):

```bash
docker-compose --profile self-hosted-sonar up -d
```

Then in `.env`:

```env
SONAR_HOST_URL=http://sonarqube:9000
SONAR_TOKEN=your-self-hosted-token
```

Create the token in SonarQube (My Account → Security → Tokens) after first login.
