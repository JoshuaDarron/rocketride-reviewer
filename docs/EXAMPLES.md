# Configuration Examples

This document shows common configuration patterns for rocketride-reviewer. The action has two configuration surfaces:

1. **GitHub Actions workflow file** (`.github/workflows/review.yml`) -- controls when the action triggers and passes credentials.
2. **Repository config file** (`.rocketride-review.yml`) -- controls review behavior, file filtering, and thresholds.

---

## 1. Default Setup

The minimal configuration with default settings. Reviews all PRs targeting `main` using full file context.

### Workflow file

```yaml
# .github/workflows/review.yml
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

No `.rocketride-review.yml` file is needed. All defaults apply:

- Review context: `full` (agents see the entire file, not just the diff)
- Target branch: `main`
- Approval threshold: `high` (auto-approve if no critical or high findings)
- Default ignore patterns for lock files, minified assets, build output, images, and fonts

---

## 2. Monorepo

For monorepos with multiple packages, you can ignore directories that are not relevant to the PR or that contain generated code specific to your project structure.

### `.rocketride-review.yml`

```yaml
# Extend the default ignore list with monorepo-specific patterns
ignore_patterns_extra:
  - "packages/legacy-app/**"
  - "packages/*/generated/**"
  - "proto/**/*.pb.go"
  - "scripts/**"
  - "tools/codegen/**"
  - "*.snapshot"
  - "**/__snapshots__/**"
```

The `ignore_patterns_extra` field adds patterns to the built-in defaults. Lock files, minified assets, and other default ignores still apply. If you want to completely replace the defaults instead, use `ignore_patterns_override`:

```yaml
# Replace all default ignore patterns with your own
ignore_patterns_override:
  - "*.lock"
  - "packages/legacy-app/**"
  - "packages/*/generated/**"
  - "dist/**"
  - "build/**"
```

---

## 3. Diff-Only Mode

For large repositories where sending full file context to the LLM agents is too expensive or slow, use diff-only mode. Agents will only see the changed lines (with surrounding diff context), not the entire file.

### Option A: Set in the workflow file

```yaml
# .github/workflows/review.yml
steps:
  - uses: rocketride-org/rocketride-reviewer@v1
    with:
      review_context: diff
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

### Option B: Set in the config file

```yaml
# .rocketride-review.yml
review_context: diff
```

If set in both places, the workflow input takes precedence over the config file.

### Trade-offs

| Mode | Pros | Cons |
|------|------|------|
| `full` | Agents understand broader context, catch cross-function issues | Higher token usage, slower reviews on large files |
| `diff` | Faster, cheaper, works well for small focused changes | Agents may miss context-dependent bugs |

---

## 4. Critical-Only Threshold

By default, the action blocks (requests changes) on both `critical` and `high` severity findings. If you want agents to only block on `critical` findings and treat `high` as informational, lower the threshold:

### `.rocketride-review.yml`

```yaml
# Only request changes for critical severity findings
# High, medium, low, and nitpick findings are posted as comments only
approval_threshold: critical
```

With this setting:

| Finding severity | Agent action |
|-----------------|-------------|
| `critical` | Agent submits **Request Changes** |
| `high` | Agent submits **Comment** (informational) |
| `medium` | Agent submits **Comment** |
| `low` | Agent submits **Comment** |
| `nitpick` | Agent submits **Comment** |

If no agent finds any `critical` issues, all three agents auto-approve the PR.

---

## 5. Custom Target Branch

By default, the action only reviews PRs targeting `main`. If your repository uses a different default branch or you want to review PRs targeting a release branch, configure the target branch.

### Option A: Set in the workflow file

```yaml
# .github/workflows/review.yml
name: RocketRide PR Review

on:
  pull_request:
    types: [opened, synchronize]
    branches: [develop]          # Match the target branch here
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
          target_branch: develop  # And here
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

Note that the `branches` filter in the workflow `on:` section and the `target_branch` action input should match. The `branches` filter controls when GitHub triggers the workflow; the `target_branch` input controls the action's internal gating logic.

### Option B: Set in the config file

```yaml
# .rocketride-review.yml
target_branch: develop
```

### Reviewing PRs to multiple branches

If you want to review PRs targeting both `main` and `develop`, you can set up the workflow to trigger on both branches and omit the `target_branch` input (or set it in the config file per-branch using different config paths):

```yaml
on:
  pull_request:
    types: [opened, synchronize]
    branches: [main, develop]
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
```

In this case, set `target_branch` to whichever branch you want the gating logic to check, or remove it to accept any branch that triggers the workflow.

---

## 6. Large PR Tuning

The action chunks large diffs to fit within LLM context windows. You can adjust the chunking thresholds based on your repository's characteristics.

### `.rocketride-review.yml` -- Larger chunk size for high-context reviews

```yaml
# Allow larger chunks (useful if your functions tend to be long)
max_chunk_lines: 800
chunk_overlap_lines: 40

# Raise the limits for repositories with many small files
max_files: 100
max_total_lines: 10000
```

### `.rocketride-review.yml` -- Stricter limits for cost control

```yaml
# Smaller chunks to reduce token usage per agent call
max_chunk_lines: 300
chunk_overlap_lines: 10

# Lower thresholds to skip very large PRs earlier
max_files: 30
max_total_lines: 3000
```

### Default values

| Setting | Default | Description |
|---------|---------|-------------|
| `max_chunk_lines` | 500 | Maximum lines per diff chunk sent to each agent |
| `chunk_overlap_lines` | 20 | Overlap between consecutive chunks for context continuity |
| `max_files` | 50 | Skip review if PR changes more files than this (after filtering) |
| `max_total_lines` | 5000 | Skip review if PR changes more total lines than this (after filtering) |

---

## 7. Combined Configuration

A comprehensive `.rocketride-review.yml` combining multiple options:

```yaml
# .rocketride-review.yml

# Use diff-only mode to save on token costs
review_context: diff

# Review PRs targeting develop
target_branch: develop

# Only block on critical findings
approval_threshold: critical

# Ignore test fixtures, migrations, and generated API clients
ignore_patterns_extra:
  - "tests/fixtures/**"
  - "migrations/**"
  - "src/api/generated/**"
  - "*.sql"
  - "**/*.test.snap"

# Tune chunking for a large codebase
max_chunk_lines: 600
chunk_overlap_lines: 30
max_files: 75
max_total_lines: 8000
```
