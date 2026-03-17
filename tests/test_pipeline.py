"""Tests for pipeline execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.errors import PipelineError
from src.models import AgentReview
from src.pipeline import PipelineRunner


@pytest.fixture()
def pipeline_dir(tmp_path: Path) -> Path:
    """Create a temporary pipeline directory with a valid pipeline file."""
    pipeline_file = tmp_path / "full_review.pipe.json"
    pipeline_file.write_text(
        '{"name": "test", "nodes": [], "edges": []}',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def conversation_pipeline_dir(tmp_path: Path) -> Path:
    """Create a temporary pipeline directory with both pipeline files."""
    full_file = tmp_path / "full_review.pipe.json"
    full_file.write_text(
        '{"name": "test", "nodes": [], "edges": []}',
        encoding="utf-8",
    )
    conv_file = tmp_path / "conversation_reply.pipe.json"
    conv_file.write_text(
        '{"name": "conversation-reply", "nodes": [], "edges": []}',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def valid_agent_response() -> dict[str, object]:
    """A valid single-agent response dict."""
    return {
        "reviewer": "claude-reviewer",
        "comments": [
            {
                "file": "src/main.py",
                "line": 10,
                "severity": "medium",
                "body": "Consider error handling here.",
            }
        ],
    }


@pytest.fixture()
def valid_three_agent_response() -> list[dict[str, object]]:
    """A valid three-agent response list."""
    return [
        {
            "reviewer": "claude-reviewer",
            "comments": [
                {
                    "file": "src/main.py",
                    "line": 10,
                    "severity": "medium",
                    "body": "Consider error handling here.",
                }
            ],
        },
        {
            "reviewer": "gpt-reviewer",
            "comments": [],
        },
        {
            "reviewer": "gemini-reviewer",
            "comments": [
                {
                    "file": "src/utils.py",
                    "line": 5,
                    "severity": "low",
                    "body": "Naming suggestion.",
                }
            ],
        },
    ]


def _make_mock_client(response: object) -> AsyncMock:
    """Create a mock RocketRideClient that returns the given response."""
    mock_client = AsyncMock()
    mock_client.use = AsyncMock(return_value="token-123")
    mock_client.send = AsyncMock(return_value=response)
    mock_client.terminate = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


class TestPipelineRunner:
    """Tests for pipeline loading and execution."""

    @pytest.mark.asyncio()
    async def test_pipeline_file_missing_raises_error(self, tmp_path: Path) -> None:
        runner = PipelineRunner(pipeline_dir=tmp_path)
        with pytest.raises(PipelineError, match="Pipeline file not found"):
            await runner.run_full_review(diff="some diff")

    @pytest.mark.asyncio()
    async def test_successful_execution_returns_tuple(
        self,
        pipeline_dir: Path,
        valid_agent_response: dict[str, object],
    ) -> None:
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        mock_client = _make_mock_client(valid_agent_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 1
        assert isinstance(reviews[0], AgentReview)
        assert reviews[0].reviewer == "claude-reviewer"
        assert len(reviews[0].comments) == 1
        assert failures == []

    @pytest.mark.asyncio()
    async def test_malformed_response_skipped_not_raised(
        self, pipeline_dir: Path
    ) -> None:
        """Malformed agent response is skipped, not raised."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        malformed = {"reviewer": 12345, "comments": "not a list"}
        mock_client = _make_mock_client(malformed)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 0
        assert "12345" in failures

    @pytest.mark.asyncio()
    async def test_one_malformed_two_valid(self, pipeline_dir: Path) -> None:
        """One malformed agent + two valid -> two reviews + one failure."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        responses = [
            {"reviewer": "claude-reviewer", "comments": []},
            {"reviewer": "bad-agent", "comments": "not a list"},
            {"reviewer": "gemini-reviewer", "comments": []},
        ]
        mock_client = _make_mock_client(responses)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 2
        assert len(failures) == 1
        assert "bad-agent" in failures

    @pytest.mark.asyncio()
    async def test_all_malformed_returns_empty_reviews(
        self, pipeline_dir: Path
    ) -> None:
        """All three agents malformed -> empty reviews + three failures."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        responses = [
            {"reviewer": "agent-a", "comments": "bad"},
            {"reviewer": "agent-b", "comments": 42},
            {"reviewer": "agent-c", "comments": None},
        ]
        mock_client = _make_mock_client(responses)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 0
        assert len(failures) == 3

    @pytest.mark.asyncio()
    async def test_sdk_error_raises_pipeline_error(self, pipeline_dir: Path) -> None:
        runner = PipelineRunner(pipeline_dir=pipeline_dir)

        mock_client = AsyncMock()
        mock_client.use = AsyncMock(side_effect=TimeoutError("SDK timeout"))
        mock_client.terminate = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="Pipeline execution failed"),
        ):
            await runner.run_full_review(diff="diff content")

    @pytest.mark.asyncio()
    async def test_token_always_terminated(
        self,
        pipeline_dir: Path,
        valid_agent_response: dict[str, object],
    ) -> None:
        """Token is terminated even on successful runs."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        mock_client = _make_mock_client(valid_agent_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            await runner.run_full_review(diff="diff content")

        mock_client.terminate.assert_called_once_with("token-123")

    @pytest.mark.asyncio()
    async def test_list_response_multiple_agents(
        self,
        pipeline_dir: Path,
        valid_three_agent_response: list[dict[str, object]],
    ) -> None:
        """Pipeline response as a list produces multiple AgentReview objects."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        mock_client = _make_mock_client(valid_three_agent_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 3
        assert failures == []

    @pytest.mark.asyncio()
    async def test_unexpected_response_type_raises_pipeline_error(
        self, pipeline_dir: Path
    ) -> None:
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        mock_client = _make_mock_client("just a string")

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="Unexpected pipeline response type"),
        ):
            await runner.run_full_review(diff="diff content")

    @pytest.mark.asyncio()
    async def test_non_dict_in_list_skipped(self, pipeline_dir: Path) -> None:
        """Non-dict items in list response are skipped."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        responses = [
            {"reviewer": "claude-reviewer", "comments": []},
            "not a dict",
            {"reviewer": "gemini-reviewer", "comments": []},
        ]
        mock_client = _make_mock_client(responses)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 2
        assert "unknown" in failures


class TestConversationReplyPipeline:
    """Tests for run_conversation_reply()."""

    @pytest.mark.asyncio()
    async def test_conversation_reply_success(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """Valid response returns reply text."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        response = {"reply": "The variable could be None if the API fails."}
        mock_client = _make_mock_client(response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reply = await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="Bot: Issue here.\nDev: Why?",
            )

        assert reply == "The variable could be None if the API fails."

    @pytest.mark.asyncio()
    async def test_conversation_reply_with_file_context(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """File context is passed to the pipeline."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        response = {"reply": "Looking at the code, line 10 is problematic."}
        mock_client = _make_mock_client(response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reply = await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="Bot: Issue.\nDev: Explain.",
                file_context="def foo():\n    return None\n",
            )

        assert "line 10" in reply
        # Verify file_context was sent
        send_call = mock_client.send.call_args
        assert "file_context" in send_call.args[1]

    @pytest.mark.asyncio()
    async def test_conversation_reply_pipeline_missing(self, tmp_path: Path) -> None:
        """Missing conversation_reply.pipe.json raises PipelineError."""
        # Only create full_review.pipe.json, not conversation_reply.pipe.json
        full_file = tmp_path / "full_review.pipe.json"
        full_file.write_text('{"name": "test"}', encoding="utf-8")

        runner = PipelineRunner(pipeline_dir=tmp_path)

        with pytest.raises(PipelineError, match="Pipeline file not found"):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="some context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_sdk_error(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """SDK error during conversation reply raises PipelineError."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)

        mock_client = AsyncMock()
        mock_client.use = AsyncMock(side_effect=TimeoutError("timeout"))
        mock_client.terminate = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="Conversation reply pipeline failed"),
        ):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_missing_reply_field(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """Response without 'reply' field raises PipelineError."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        response = {"text": "wrong field name"}
        mock_client = _make_mock_client(response)

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="missing 'reply' field"),
        ):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_empty_reply(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """Empty reply string raises PipelineError."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        response = {"reply": "   "}
        mock_client = _make_mock_client(response)

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="missing 'reply' field"),
        ):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_non_dict_response(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """Non-dict response raises PipelineError."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        mock_client = _make_mock_client("just a string")

        with (
            patch("src.pipeline.RocketRideClient", return_value=mock_client),
            pytest.raises(PipelineError, match="Unexpected conversation response type"),
        ):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_token_terminated(
        self, conversation_pipeline_dir: Path
    ) -> None:
        """Token is terminated after conversation reply."""
        runner = PipelineRunner(pipeline_dir=conversation_pipeline_dir)
        response = {"reply": "Here is my response."}
        mock_client = _make_mock_client(response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

        mock_client.terminate.assert_called_once_with("token-123")
