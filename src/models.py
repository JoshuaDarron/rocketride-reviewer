"""Pydantic models for structured data passed across module boundaries.

All structured data (review comments, agent responses, configuration)
is represented as Pydantic models. Never pass raw dicts across modules.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    """Comment severity levels, ordered from most to least severe."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NITPICK = "nitpick"


class CommentStatus(StrEnum):
    """Whether a comment adds a new issue or resolves an existing one."""

    ADD = "add"
    RESOLVE = "resolve"


class ReviewComment(BaseModel):
    """A single review comment from an agent."""

    file: str = Field(description="Relative file path within the repository")
    line: int = Field(ge=1, description="Line number in the diff")
    severity: Severity = Field(description="Comment severity level")
    status: CommentStatus = Field(
        default=CommentStatus.ADD,
        description="Whether this adds a new comment or resolves one",
    )
    body: str = Field(
        min_length=1,
        max_length=65536,
        description="Full text of the review comment",
    )

    @field_validator("file")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Reject empty, absolute, and path-traversal file paths."""
        if not v or not v.strip():
            msg = "file path must not be empty"
            raise ValueError(msg)
        if v.startswith("/") or v.startswith("\\"):
            msg = "file path must be relative, not absolute"
            raise ValueError(msg)
        if ".." in v.split("/"):
            msg = "file path must not contain '..' traversal"
            raise ValueError(msg)
        return v


class AgentReview(BaseModel):
    """Complete review output from a single agent."""

    reviewer: str = Field(description="Agent name (e.g. claude-reviewer)")
    comments: list[ReviewComment] = Field(default_factory=list)


class ReviewConfig(BaseModel):
    """Configuration loaded from environment and .rocketride-review.yml."""

    review_context: Literal["full", "diff"] = Field(
        default="full",
        description="Whether to include full file context or diff only",
    )
    target_branch: str = Field(
        default="main",
        description="Branch that PRs must target to trigger reviews",
    )
    approval_threshold: Literal["critical", "high"] = Field(
        default="high",
        description="Severity at or above which auto-approval is blocked",
    )
    ignore_patterns_extra: list[str] = Field(
        default_factory=list,
        description="Additional file patterns to ignore (extends defaults)",
    )
    ignore_patterns_override: list[str] | None = Field(
        default=None,
        description="If set, replaces the default ignore patterns entirely",
    )
    max_chunk_lines: int = Field(
        default=500, ge=50, description="Max lines per diff chunk"
    )
    chunk_overlap_lines: int = Field(
        default=20, ge=0, description="Overlap context between segments"
    )
    max_files: int = Field(
        default=50, ge=1, description="Max changed files before skipping review"
    )
    max_total_lines: int = Field(
        default=5000, ge=100, description="Max total changed lines before skipping"
    )
