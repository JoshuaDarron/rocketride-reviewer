# Contributing to rocketride-reviewer

Thank you for your interest in contributing. This guide covers the development setup, coding standards, and pull request process.

---

## Development Setup

### Prerequisites

- Python 3.12 or later
- Docker (for running the RocketRide engine locally)
- Git

### Clone and install

```bash
git clone https://github.com/rocketride-org/rocketride-reviewer.git
cd rocketride-reviewer
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

The `requirements-dev.txt` file includes all production dependencies plus testing and linting tools.

### Verify the setup

```bash
# Run tests
pytest tests/ -v

# Run linter
ruff check src/ tests/

# Run formatter check
black --check src/ tests/

# Run type checker
mypy src/
```

All four commands should pass cleanly before you submit a PR.

---

## Code Style

This project enforces consistent style through automated tooling:

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **Black** | Code formatting | 88 character line length (default) |
| **Ruff** | Linting | Default rules plus `I`, `UP`, `B`, `SIM`, `PTH` rule sets |
| **mypy** | Type checking | Strict mode |

### Key rules

- **Type hints** are required on all function signatures. Use `from __future__ import annotations` at the top of every module.
- **Google-style docstrings** are required on all public functions and classes.
- **f-strings** are preferred over `.format()` or `%` formatting.
- **Pydantic models** are used for all structured data crossing module boundaries. Do not pass raw dicts.
- **`pathlib.Path`** is used instead of `os.path` for file operations.
- **Imports** are sorted by Ruff/isort: standard library first, then third-party, then local.

---

## Testing

### Expectations

- Every source module in `src/` has a corresponding test module in `tests/`. If you add a new source module, add a test module for it.
- Unit tests mock all external dependencies (GitHub API, RocketRide SDK, LLM APIs). Tests must run fast and offline.
- Integration tests that hit real services belong in `tests/integration/` and are marked with `@pytest.mark.integration`. These do not run in standard CI.

### Running tests

```bash
# All unit tests
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=src --cov-report=term-missing

# Single module
pytest tests/test_aggregator.py -v
```

### Shared fixtures

Common test data is defined in `tests/conftest.py`. Use existing fixtures when possible and add new ones there if they would benefit multiple test modules.

---

## Pull Request Process

1. **Branch from `main`** for all work.
2. **Keep changes focused.** One logical change per PR. If a PR touches many unrelated areas, consider splitting it.
3. **Run all checks locally** before pushing:
   ```bash
   ruff check src/ tests/
   black --check src/ tests/
   mypy src/
   pytest tests/ -v
   ```
4. **Write a clear PR description** explaining what changed and why. Link to any relevant issues.
5. **CI must pass.** The CI workflow runs linting, type checking, and tests on every PR. All checks must be green before merging.

### Commit messages

Use short, imperative-style messages:

- "Add aggregator dedup logic"
- "Fix agent timeout handling"
- "Update pipeline schema"

---

## Architecture Overview

Each module in `src/` has a single responsibility:

| Module | Responsibility |
|--------|---------------|
| `main.py` | Entry point: event detection, gating logic, orchestration |
| `github_client.py` | GitHub API wrapper: fetch diffs, post comments, submit reviews |
| `engine.py` | RocketRide Docker engine lifecycle: start, health check, teardown |
| `pipeline.py` | Pipeline execution for full review and conversation reply modes |
| `aggregator.py` | Comment deduplication across the three agents |
| `reviewer.py` | Review posting under each GitHub App identity |
| `chunker.py` | Large PR diff splitting and line number remapping |
| `config.py` | Configuration loading, constants, model versions, agent routing |
| `models.py` | Pydantic models for review comments, agent responses, and config |
| `filters.py` | File ignore pattern matching |
| `retry.py` | Retry with exponential backoff for transient errors |
| `errors.py` | Exception hierarchy for all project-specific errors |

For detailed coding conventions, architecture decisions, and project guidelines, see [CLAUDE.md](.claude/CLAUDE.md).

---

## Reporting Issues

If you find a bug or have a feature request, open an issue on GitHub with:

- A clear description of the problem or proposed change
- Steps to reproduce (for bugs)
- Expected vs. actual behavior (for bugs)
- Relevant logs or error messages if available
