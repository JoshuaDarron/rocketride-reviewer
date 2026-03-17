"""Tests for pipeline execution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.errors import PipelineError
from src.models import AgentReview
from src.pipeline import PipelineRunner


@pytest.fixture()
def pipeline_dir(tmp_path: Path) -> Path:
    """Create a temporary pipeline directory with a valid pipeline file."""
    pipeline_file = tmp_path / "full-review.pipe.json"
    pipeline_file.write_text(
        '{"name": "test", "nodes": [], "edges": []}',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def conversation_pipeline_dir(tmp_path: Path) -> Path:
    """Create a temporary pipeline directory with all pipeline files."""
    full_file = tmp_path / "full-review.pipe.json"
    full_file.write_text(
        '{"name": "test", "nodes": [], "edges": []}',
        encoding="utf-8",
    )
    for filename in (
        "conversation-reply-claude.pipe.json",
        "conversation-reply-openai.pipe.json",
        "conversation-reply-gemini.pipe.json",
    ):
        conv_file = tmp_path / filename
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


@pytest.fixture()
def valid_lane_response() -> dict[str, object]:
    """A valid named-lane response dict (no reviewer keys in lane data)."""
    return {
        "claude": {
            "comments": [
                {
                    "file": "src/main.py",
                    "line": 10,
                    "severity": "medium",
                    "body": "Consider error handling here.",
                }
            ],
        },
        "openai": {
            "comments": [],
        },
        "gemini": {
            "comments": [
                {
                    "file": "src/utils.py",
                    "line": 5,
                    "severity": "low",
                    "body": "Naming suggestion.",
                }
            ],
        },
    }


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
        """Missing per-agent pipeline file raises PipelineError."""
        # Only create full-review.pipe.json, not per-agent conversation files
        full_file = tmp_path / "full-review.pipe.json"
        full_file.write_text('{"name": "test"}', encoding="utf-8")

        runner = PipelineRunner(pipeline_dir=tmp_path)

        with pytest.raises(PipelineError, match="Pipeline file not found"):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="some context",
            )

    @pytest.mark.asyncio()
    async def test_conversation_reply_unknown_agent(self, tmp_path: Path) -> None:
        """Unknown agent_node_id raises PipelineError."""
        runner = PipelineRunner(pipeline_dir=tmp_path)

        with pytest.raises(PipelineError, match="Unknown agent node ID"):
            await runner.run_conversation_reply(
                agent_node_id="nonexistent-agent",
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


class TestLaneResponseParsing:
    """Tests for named-lane response format parsing."""

    @pytest.mark.asyncio()
    async def test_lane_response_parsed_correctly(
        self,
        pipeline_dir: Path,
        valid_lane_response: dict[str, object],
    ) -> None:
        """Named-lane response produces correct AgentReview objects."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        mock_client = _make_mock_client(valid_lane_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 3
        assert failures == []
        reviewer_names = {r.reviewer for r in reviews}
        assert reviewer_names == {"claude-reviewer", "gpt-reviewer", "gemini-reviewer"}

    @pytest.mark.asyncio()
    async def test_lane_response_injects_reviewer_name(
        self,
        pipeline_dir: Path,
    ) -> None:
        """Reviewer name is injected from LANE_TO_REVIEWER mapping."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        lane_response = {
            "openai": {"comments": []},
        }
        mock_client = _make_mock_client(lane_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 1
        assert reviews[0].reviewer == "gpt-reviewer"

    @pytest.mark.asyncio()
    async def test_malformed_lane_data_skipped(
        self,
        pipeline_dir: Path,
    ) -> None:
        """Malformed data in a lane is skipped, not raised."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        lane_response = {
            "claude": {"comments": []},
            "openai": "not a dict",
            "gemini": {"comments": []},
        }
        mock_client = _make_mock_client(lane_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 2
        assert "gpt-reviewer" in failures

    @pytest.mark.asyncio()
    async def test_lane_with_invalid_comments_skipped(
        self,
        pipeline_dir: Path,
    ) -> None:
        """Lane with invalid comments field is skipped."""
        runner = PipelineRunner(pipeline_dir=pipeline_dir)
        lane_response = {
            "claude": {"comments": "not a list"},
        }
        mock_client = _make_mock_client(lane_response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            reviews, failures = await runner.run_full_review(diff="diff content")

        assert len(reviews) == 0
        assert "claude-reviewer" in failures


def _make_pipeline_with_llm(provider: str, profile: str) -> dict[str, object]:
    """Create a minimal pipeline dict with one LLM component."""
    return {
        "name": "test",
        "components": [
            {
                "id": f"{provider}_1",
                "provider": provider,
                "config": {
                    "profile": profile,
                    profile: {"apikey": "REPLACE_ME"},
                },
            }
        ],
    }


class TestInjectApiKeys:
    """Tests for _inject_api_keys API key injection."""

    def test_injects_anthropic_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INPUT_ANTHROPIC_API_KEY", "sk-ant-secret")
        pipeline = _make_pipeline_with_llm("llm_anthropic", "claude-sonnet-4-6")

        PipelineRunner._inject_api_keys(pipeline)

        apikey = pipeline["components"][0]["config"]["claude-sonnet-4-6"]["apikey"]
        assert apikey == "sk-ant-secret"

    def test_injects_openai_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INPUT_OPENAI_API_KEY", "sk-openai-secret")
        pipeline = _make_pipeline_with_llm("llm_openai", "openai-5-2")

        PipelineRunner._inject_api_keys(pipeline)

        apikey = pipeline["components"][0]["config"]["openai-5-2"]["apikey"]
        assert apikey == "sk-openai-secret"

    def test_injects_gemini_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INPUT_GOOGLE_API_KEY", "google-secret")
        pipeline = _make_pipeline_with_llm("llm_gemini", "gemini-3-pro")

        PipelineRunner._inject_api_keys(pipeline)

        apikey = pipeline["components"][0]["config"]["gemini-3-pro"]["apikey"]
        assert apikey == "google-secret"

    def test_missing_env_var_raises_pipeline_error(self) -> None:
        pipeline = _make_pipeline_with_llm("llm_anthropic", "claude-sonnet-4-6")

        with pytest.raises(PipelineError, match="INPUT_ANTHROPIC_API_KEY"):
            PipelineRunner._inject_api_keys(pipeline)

    def test_skips_non_llm_components(self) -> None:
        pipeline = {
            "name": "test",
            "components": [
                {"id": "webhook_1", "provider": "webhook", "config": {}},
                {"id": "question_1", "provider": "question", "config": {}},
            ],
        }
        # Should not raise
        PipelineRunner._inject_api_keys(pipeline)

    def test_skips_already_set_keys(self) -> None:
        """Components with apikey != REPLACE_ME are left unchanged."""
        pipeline = {
            "name": "test",
            "components": [
                {
                    "id": "llm_anthropic_1",
                    "provider": "llm_anthropic",
                    "config": {
                        "profile": "claude-sonnet-4-6",
                        "claude-sonnet-4-6": {"apikey": "already-set"},
                    },
                }
            ],
        }
        PipelineRunner._inject_api_keys(pipeline)

        apikey = pipeline["components"][0]["config"]["claude-sonnet-4-6"]["apikey"]
        assert apikey == "already-set"

    def test_injects_all_three_in_full_review(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All three providers get keys injected in a full-review pipeline."""
        monkeypatch.setenv("INPUT_ANTHROPIC_API_KEY", "ant-key")
        monkeypatch.setenv("INPUT_OPENAI_API_KEY", "oai-key")
        monkeypatch.setenv("INPUT_GOOGLE_API_KEY", "goog-key")

        pipeline = {
            "name": "full-review",
            "components": [
                {
                    "id": "llm_anthropic_1",
                    "provider": "llm_anthropic",
                    "config": {
                        "profile": "claude-sonnet-4-6",
                        "claude-sonnet-4-6": {"apikey": "REPLACE_ME"},
                    },
                },
                {
                    "id": "llm_openai_1",
                    "provider": "llm_openai",
                    "config": {
                        "profile": "openai-5-2",
                        "openai-5-2": {"apikey": "REPLACE_ME"},
                    },
                },
                {
                    "id": "llm_gemini_1",
                    "provider": "llm_gemini",
                    "config": {
                        "profile": "gemini-3-pro",
                        "gemini-3-pro": {"apikey": "REPLACE_ME"},
                    },
                },
            ],
        }

        PipelineRunner._inject_api_keys(pipeline)

        assert (
            pipeline["components"][0]["config"]["claude-sonnet-4-6"]["apikey"]
            == "ant-key"
        )
        assert pipeline["components"][1]["config"]["openai-5-2"]["apikey"] == "oai-key"
        assert (
            pipeline["components"][2]["config"]["gemini-3-pro"]["apikey"] == "goog-key"
        )

    def test_no_components_key_is_safe(self) -> None:
        """Pipeline without components key does not raise."""
        pipeline: dict[str, object] = {"name": "empty"}
        PipelineRunner._inject_api_keys(pipeline)

    @pytest.mark.asyncio()
    async def test_keys_injected_during_full_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API keys are injected into the pipeline dict sent to the SDK."""
        monkeypatch.setenv("INPUT_ANTHROPIC_API_KEY", "ant-key")

        pipeline_content = _make_pipeline_with_llm("llm_anthropic", "claude-sonnet-4-6")
        pipeline_file = tmp_path / "full-review.pipe.json"
        pipeline_file.write_text(json.dumps(pipeline_content), encoding="utf-8")

        runner = PipelineRunner(pipeline_dir=tmp_path)
        response = {"reviewer": "claude-reviewer", "comments": []}
        mock_client = _make_mock_client(response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            await runner.run_full_review(diff="diff content")

        # Verify the pipeline dict passed to client.use() has the key injected
        used_pipeline = mock_client.use.call_args.args[0]
        apikey = used_pipeline["components"][0]["config"]["claude-sonnet-4-6"]["apikey"]
        assert apikey == "ant-key"

    @pytest.mark.asyncio()
    async def test_keys_injected_during_conversation_reply(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API keys are injected into conversation reply pipelines."""
        monkeypatch.setenv("INPUT_ANTHROPIC_API_KEY", "ant-key")

        pipeline_content = _make_pipeline_with_llm("llm_anthropic", "claude-sonnet-4-6")
        for filename in (
            "conversation-reply-claude.pipe.json",
            "conversation-reply-openai.pipe.json",
            "conversation-reply-gemini.pipe.json",
        ):
            (tmp_path / filename).write_text(
                json.dumps(pipeline_content), encoding="utf-8"
            )

        runner = PipelineRunner(pipeline_dir=tmp_path)
        response = {"reply": "Here is my response."}
        mock_client = _make_mock_client(response)

        with patch("src.pipeline.RocketRideClient", return_value=mock_client):
            await runner.run_conversation_reply(
                agent_node_id="claude-reviewer",
                thread_context="context",
            )

        used_pipeline = mock_client.use.call_args.args[0]
        apikey = used_pipeline["components"][0]["config"]["claude-sonnet-4-6"]["apikey"]
        assert apikey == "ant-key"
