# GitHub App Setup Guide

Step-by-step instructions for creating the three GitHub Apps required by rocketride-reviewer. Each AI reviewer agent (Claude, GPT, Gemini) needs its own GitHub App so it can post reviews under its own identity.

---

## Prerequisites

Before starting, make sure you have:

1. **GitHub account with admin access** to the organization or repository where you want to install the action. You need admin access to create GitHub Apps and configure repository secrets.

2. **API keys from all three LLM providers:**
   - **Anthropic API key** -- used by the Claude reviewer agent and the aggregator. Get one at [console.anthropic.com](https://console.anthropic.com/).
   - **OpenAI API key** -- used by the GPT reviewer agent. Get one at [platform.openai.com](https://platform.openai.com/).
   - **Google AI API key** -- used by the Gemini reviewer agent. Get one at [aistudio.google.com](https://aistudio.google.com/).

3. **Sufficient API credits** on each provider account. Each PR review makes one API call per agent, plus one aggregator call. Large PRs that require chunking will make multiple calls per agent.

---

## Step 1: Create the GitHub Apps

You need to create three separate GitHub Apps. The process is identical for each -- only the name changes. Repeat the steps below three times, once for each of these app names:

- `claude-reviewer`
- `gpt-reviewer`
- `gemini-reviewer`

### 1.1 Navigate to GitHub App creation

1. Go to your GitHub **Settings**:
   - For an **organization**: `https://github.com/organizations/<YOUR_ORG>/settings/apps`
   - For a **personal account**: `https://github.com/settings/apps`
2. Click **Developer settings** in the left sidebar (personal accounts) or find **GitHub Apps** directly (organizations).
3. Click **New GitHub App**.

### 1.2 Fill in the app details

| Field | Value |
|-------|-------|
| **GitHub App name** | `claude-reviewer` (or `gpt-reviewer` / `gemini-reviewer`) |
| **Homepage URL** | Your repository URL (e.g., `https://github.com/your-org/your-repo`) |
| **Webhook** | **Uncheck** "Active". The GitHub Action handles events via workflow triggers, not webhooks. |

### 1.3 Set permissions

Under **Repository permissions**, set the following:

| Permission | Access level |
|------------|-------------|
| **Pull requests** | Read & Write |
| **Issues** | Read & Write |
| **Contents** | Read |

Leave all other permissions at their defaults (No access).

### 1.4 Subscribe to events

Under **Subscribe to events**, check:

- **Pull request**
- **Issue comment**
- **Pull request review comment**

### 1.5 Set installation scope

Under **Where can this GitHub App be installed?**, select:

- **Only on this account**

This restricts the app to your organization or personal account. You can change this later if you want to share the app across organizations.

### 1.6 Create the app

Click **Create GitHub App**.

### 1.7 Record the App ID

After creation, you are taken to the app's settings page. Note the **App ID** displayed near the top of the page. You will need this value as a repository secret.

### 1.8 Generate a private key

1. Scroll down to the **Private keys** section.
2. Click **Generate a private key**.
3. A `.pem` file will be downloaded to your computer. Keep this file safe -- you will need its contents as a repository secret.

> **Important:** The private key file is only downloadable once at generation time. If you lose it, you will need to generate a new one and update your repository secrets.

### 1.9 Repeat for the remaining apps

Repeat steps 1.1 through 1.8 for the other two app names. When you are done, you should have:

- Three GitHub Apps: `claude-reviewer`, `gpt-reviewer`, `gemini-reviewer`
- Three App IDs (one per app)
- Three private key `.pem` files (one per app)

---

## Step 2: Install the Apps on Your Repository

Each app must be installed on the repository (or repositories) where you want PR reviews to run.

1. Go to the app's settings page:
   - Organization: `https://github.com/organizations/<YOUR_ORG>/settings/apps/<APP_NAME>`
   - Personal: `https://github.com/settings/apps/<APP_NAME>`
2. Click **Install App** in the left sidebar.
3. Select your account or organization.
4. Choose **Only select repositories** and pick the repository where you want reviews.
5. Click **Install**.

Repeat for all three apps.

---

## Step 3: Configure Repository Secrets

The action reads credentials from repository secrets. You need to add 12 secrets total: 3 LLM API keys + 3 App IDs + 3 App private keys + 3 additional secrets (the private keys).

### 3.1 Navigate to secrets

1. Go to your repository on GitHub.
2. Click **Settings** > **Secrets and variables** > **Actions**.
3. Click **New repository secret** for each entry below.

### 3.2 Add all required secrets

| Secret name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (starts with `sk-ant-`) |
| `OPENAI_API_KEY` | Your OpenAI API key (starts with `sk-`) |
| `GOOGLE_API_KEY` | Your Google AI API key |
| `CLAUDE_APP_ID` | App ID from the `claude-reviewer` GitHub App |
| `CLAUDE_APP_PRIVATE_KEY` | Full contents of the `claude-reviewer` `.pem` file |
| `GPT_APP_ID` | App ID from the `gpt-reviewer` GitHub App |
| `GPT_APP_PRIVATE_KEY` | Full contents of the `gpt-reviewer` `.pem` file |
| `GEMINI_APP_ID` | App ID from the `gemini-reviewer` GitHub App |
| `GEMINI_APP_PRIVATE_KEY` | Full contents of the `gemini-reviewer` `.pem` file |

For the private key secrets, open each `.pem` file in a text editor and copy the **entire contents** including the `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----` lines. Paste the full text as the secret value.

---

## Step 4: Add the Workflow File

Create `.github/workflows/review.yml` in your repository:

```yaml
name: RocketRide PR Review

on:
  pull_request:
    types: [opened, synchronize]
    branches: [main]
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: rocketride-org/rocketride-reviewer@v1
        with:
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          google_api_key: ${{ secrets.GOOGLE_API_KEY }}
          claude_app_id: ${{ secrets.CLAUDE_APP_ID }}
          claude_app_private_key: ${{ secrets.CLAUDE_APP_PRIVATE_KEY }}
          gpt_app_id: ${{ secrets.GPT_APP_ID }}
          gpt_app_private_key: ${{ secrets.GPT_APP_PRIVATE_KEY }}
          gemini_app_id: ${{ secrets.GEMINI_APP_ID }}
          gemini_app_private_key: ${{ secrets.GEMINI_APP_PRIVATE_KEY }}
```

---

## Step 5: Verify the Setup

1. **Open a test pull request** targeting your `main` branch with a small code change.
2. **Wait a few minutes.** The GitHub Action workflow will trigger automatically.
3. **Check the Actions tab** in your repository to see the workflow run.
4. **Check the PR** for review comments from the three bot accounts.

If everything is configured correctly, you should see review comments from `claude-reviewer[bot]`, `gpt-reviewer[bot]`, and `gemini-reviewer[bot]` within a few minutes.

To test conversation replies, reply to one of the agent's comments. Only the agent you replied to should respond.

---

## Troubleshooting

### The workflow does not trigger

- **Check the workflow file location.** It must be at `.github/workflows/review.yml` (or any `.yml` file in that directory).
- **Check the event triggers.** Make sure `pull_request`, `issue_comment`, and `pull_request_review_comment` are all listed in the `on:` section.
- **Check the target branch.** By default, the action only reviews PRs targeting `main`. If your default branch is `master` or `develop`, set `target_branch` in your `.rocketride-review.yml` or pass `target_branch` as an action input.

### The workflow runs but no reviews are posted

- **Check the workflow logs.** Go to the Actions tab, click the workflow run, and expand the "Run RocketRide Reviewer" step. Look for error messages.
- **Check that all secrets are configured.** Missing or incorrectly named secrets will cause authentication failures. The action will post a comment on the PR explaining which credentials are missing.
- **Check App installation.** Each GitHub App must be installed on the specific repository. Go to the app's settings and verify it is installed and has access to the target repository.

### Authentication errors (401 or 403)

- **Expired private key.** GitHub App private keys do not expire, but if you regenerated a key, the old one is invalidated. Make sure the secret contains the current key.
- **Wrong App ID.** Verify that each `*_APP_ID` secret matches the correct app. A common mistake is swapping the Claude and GPT app IDs.
- **Incorrect private key format.** The secret must contain the full `.pem` file contents including the header and footer lines. Make sure there are no extra spaces or line breaks at the beginning or end.
- **Insufficient permissions.** If the app was created with incorrect permissions, go to the app's settings page, update the permissions under **Permissions & events**, and then re-install the app on your repository (permission changes require re-installation approval).

### One agent posts reviews but others do not

- **Check individual API keys.** Each agent uses a different LLM provider. If only the Claude agent works, verify that `OPENAI_API_KEY` and `GOOGLE_API_KEY` are correct and have sufficient credits.
- **Check the workflow logs for agent-specific errors.** The action logs which agents succeeded and which failed. Agent failures are independent -- one agent failing does not block the others.

### Conversation replies do not work

- **Make sure `issue_comment` and `pull_request_review_comment` are in your workflow triggers.** Without these events, the action will not see developer replies.
- **Check that you are replying to a bot comment, not a human comment.** The conversation reply pipeline only activates when the parent comment was authored by one of the three reviewer bots.
- **Loop prevention.** If a bot's own comment triggers the workflow, the action exits immediately to prevent infinite loops. This is expected behavior.

### Rate limiting

- **LLM API rate limits.** If an agent hits a rate limit, the action retries up to 3 times with exponential backoff. If all retries fail, that agent's review is skipped and a comment is posted explaining the issue.
- **GitHub API rate limits.** GitHub App installation tokens have a rate limit of 5,000 requests per hour. This is more than sufficient for normal usage. If you are running reviews on many PRs simultaneously, you may need to stagger them.

### PR is too large to review

- If the PR exceeds the configured thresholds (`max_files: 50` or `max_total_lines: 5000` by default), the action posts a summary comment and skips the review. You can adjust these thresholds in `.rocketride-review.yml`. See the [configuration section in the README](../README.md#configuration) for details.
