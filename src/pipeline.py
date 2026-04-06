"""Pipeline execution for full review and conversation modes.

Loads pipeline JSON, starts pipelines via the RocketRide SDK, sends
diff data, polls for completion, and receives structured agent responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from rocketride import RocketRideClient
from rocketride.types.task import TASK_STATE

from src.config import (
    CONVERSATION_PIPELINE_FILES,
    ENGINE_AUTH_KEY,
    ENGINE_PORT,
    FULL_REVIEW_PIPELINE_FILE,
    LANE_TO_REVIEWER,
    LLM_PROVIDER_API_KEY_ENV,
    PIPELINE_POLL_INTERVAL,
    PIPELINE_POLL_TIMEOUT,
)
from src.errors import PipelineError
from src.models import AgentReview

logger = logging.getLogger(__name__)

# Keys that belong to the TASK_STATUS envelope, not the pipeline output.
_STATUS_METADATA_KEYS: set[str] = {
    "name",
    "project_id",
    "source",
    "completed",
    "state",
    "startTime",
    "endTime",
    "debuggerAttached",
    "status",
    "warnings",
    "errors",
    "currentObject",
    "currentSize",
    "notes",
    "totalSize",
    "totalCount",
    "completedSize",
    "completedCount",
    "failedSize",
    "failedCount",
    "wordsSize",
    "wordsCount",
    "rateSize",
    "rateCount",
    "serviceUp",
    "exitCode",
    "exitMessage",
    "pipeflow",
    "metrics",
    "tokens",
}


class PipelineRunner:
    """Executes RocketRide pipelines and collects agent responses.

    Args:
        pipeline_dir: Directory containing pipeline JSON files.
            Defaults to ``pipelines/`` relative to the project root.
    """

    def __init__(self, pipeline_dir: Path | None = None) -> None:
        if pipeline_dir is None:
            pipeline_dir = Path(__file__).resolve().parent.parent / "pipelines"
        self._pipeline_dir = pipeline_dir

    @staticmethod
    def _strip_status_metadata(status: object) -> object:
        """Remove TASK_STATUS envelope keys from the pipeline result.

        The completed status dict may contain both the pipeline output
        and engine metadata. This strips known metadata keys so only
        pipeline-produced data remains. Non-dict values are returned
        as-is.
        """
        if not isinstance(status, dict):
            return status
        return {k: v for k, v in status.items() if k not in _STATUS_METADATA_KEYS}

    @staticmethod
    def _inject_api_keys(pipeline: dict[str, Any]) -> dict[str, Any]:
        """Replace ``REPLACE_ME`` API key placeholders with real values.

        Iterates over the pipeline's ``components`` list and, for each LLM
        component whose ``provider`` is in ``LLM_PROVIDER_API_KEY_ENV``,
        replaces any ``"apikey": "REPLACE_ME"`` value with the corresponding
        environment variable.

        Args:
            pipeline: Parsed pipeline definition dict (mutated in place).

        Returns:
            The same pipeline dict, with API keys injected.

        Raises:
            PipelineError: If a required API key environment variable is
                not set.
        """
        for component in pipeline.get("components", []):
            provider = component.get("provider", "")
            env_var = LLM_PROVIDER_API_KEY_ENV.get(provider)
            if env_var is None:
                continue

            config = component.get("config", {})
            profile = config.get("profile", "")
            profile_config = config.get(profile, {})

            if profile_config.get("apikey") != "REPLACE_ME":
                continue

            api_key = os.environ.get(env_var)
            if not api_key:
                msg = (
                    f"Environment variable {env_var} is required for "
                    f"provider {provider} but is not set"
                )
                raise PipelineError(msg)

            profile_config["apikey"] = api_key

        return pipeline

    async def _execute_pipeline(
        self,
        pipeline_data: dict[str, Any],
        input_data: dict[str, Any],
        error_prefix: str,
    ) -> dict[str, Any]:
        """Start a pipeline, send data, poll for completion, and return results.

        Writes the pipeline definition to a temporary file and passes it via
        ``filepath=`` so the engine can load it natively. Uses the ``pipe()``
        context manager for data transfer when available, falling back to
        polling ``get_task_status()`` for result retrieval.

        Args:
            pipeline_data: Parsed pipeline configuration dict.
            input_data: Input data to send to the pipeline.
            error_prefix: Prefix for error messages on failure.

        Returns:
            The pipeline result from the completed task status.

        Raises:
            PipelineError: If the pipeline fails to start, times out, or
                returns a failed status.
        """
        token: str | None = None
        tmp_file: str | None = None
        try:
            # Write pipeline to a temp file so the engine loads it natively
            fd, tmp_file = tempfile.mkstemp(suffix=".pipe.json")
            os.close(fd)
            Path(tmp_file).write_text(json.dumps(pipeline_data), encoding="utf-8")

            async with RocketRideClient(
                f"http://localhost:{ENGINE_PORT}",
                auth=ENGINE_AUTH_KEY,
            ) as client:
                try:
                    result = await client.use(filepath=tmp_file)
                    token = result["token"]
                    logger.info("Pipeline started with token: %s", token)

                    # Use pipe() context manager for data transfer
                    pipe_result: dict[str, Any] | None = None
                    async with await client.pipe(
                        token, mimetype="application/json"
                    ) as pipe:
                        await pipe.write(json.dumps(input_data).encode())
                    logger.info(
                        "Data sent to pipeline via pipe(), polling for completion"
                    )

                    # pipe.close() may return result data; check for it
                    if hasattr(pipe, "result") and isinstance(pipe.result, dict):
                        pipe_result = pipe.result

                    if pipe_result and any(
                        k not in _STATUS_METADATA_KEYS for k in pipe_result
                    ):
                        logger.info("Got result from pipe(), skipping poll")
                        return pipe_result

                    return await self._poll_for_result(client, token)
                finally:
                    if token is not None:
                        try:
                            await client.terminate(token)
                        except (PipelineError, ConnectionError, OSError):
                            logger.warning("Failed to terminate pipeline token")
        except PipelineError:
            raise
        except (ConnectionError, OSError, TimeoutError) as e:
            msg = f"{error_prefix}: {e}"
            raise PipelineError(msg) from e
        finally:
            if tmp_file is not None:
                try:
                    Path(tmp_file).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Failed to clean up temp pipeline file")

    async def _poll_for_result(
        self,
        client: RocketRideClient,
        token: str,
    ) -> dict[str, Any]:
        """Poll get_task_status until the pipeline completes or times out.

        Args:
            client: Connected RocketRideClient instance.
            token: Pipeline task token.

        Returns:
            The result data from the completed task status.

        Raises:
            PipelineError: If the pipeline fails or times out.
        """
        start_time = time.monotonic()
        deadline = start_time + PIPELINE_POLL_TIMEOUT

        while time.monotonic() < deadline:
            raw = await client.get_task_status(token)

            # Normalise to dict regardless of SDK return type
            if isinstance(raw, dict):
                status = raw
            elif hasattr(raw, "model_dump"):
                status = raw.model_dump()
            else:
                msg = f"Unexpected task status type from SDK: {type(raw).__name__}"
                raise PipelineError(msg)

            state = status.get("state", 0)

            logger.info(
                "Pipeline status: %s (%.1fs elapsed)",
                state,
                time.monotonic() - start_time,
            )

            if state == TASK_STATE.COMPLETED.value:
                logger.info("Pipeline completed successfully")
                logger.debug("Pipeline result: %s", status)
                return status

            errors = status.get("errors", [])
            if errors:
                error = errors[-1]
                msg = f"Pipeline failed: {error}"
                raise PipelineError(msg)

            if state == TASK_STATE.CANCELLED.value:
                msg = "Pipeline was cancelled unexpectedly"
                raise PipelineError(msg)

            await asyncio.sleep(PIPELINE_POLL_INTERVAL)

        elapsed = time.monotonic() - start_time
        msg = f"Pipeline did not complete within {elapsed:.1f}s"
        raise PipelineError(msg)

    async def run_full_review(
        self,
        diff: str,
        file_context: dict[str, str] | None = None,
        review_mode: str = "full",
    ) -> tuple[list[AgentReview], list[str]]:
        """Run the full review pipeline.

        Args:
            diff: Unified diff of the pull request.
            file_context: Optional mapping of file paths to content.
            review_mode: Either ``"full"`` or ``"diff"``.

        Returns:
            A tuple of (valid AgentReview objects, names of failed agents).

        Raises:
            PipelineError: If the pipeline file is missing or execution
                fails.
        """
        pipeline_path = self._pipeline_dir / FULL_REVIEW_PIPELINE_FILE
        if not pipeline_path.is_file():
            msg = f"Pipeline file not found: {pipeline_path}"
            raise PipelineError(msg)

        pipeline_data = json.loads(pipeline_path.read_text(encoding="utf-8"))
        self._inject_api_keys(pipeline_data)

        input_data: dict[str, object] = {
            "diff": diff,
            "review_mode": review_mode,
        }
        if file_context:
            input_data["file_context"] = file_context

        raw_status = await self._execute_pipeline(
            pipeline_data, input_data, "Pipeline execution failed"
        )
        logger.info(
            "Full review pipeline raw status: %s",
            json.dumps(raw_status, default=str)[:2000],
        )
        response = self._strip_status_metadata(raw_status)
        logger.info(
            "Full review pipeline response (stripped): %s",
            json.dumps(response, default=str)[:2000],
        )
        return self._parse_response(response)

    def _parse_response(self, response: object) -> tuple[list[AgentReview], list[str]]:
        """Parse and validate pipeline response into AgentReview objects.

        Supports two response formats:
        - **Named-lane dict**: Keys match ``LANE_TO_REVIEWER`` (e.g.
          ``{"claude": {...}, "openai": {...}, "gemini": {...}}``). Each
          lane value is parsed and the ``reviewer`` field is injected from
          the lane mapping.
        - **Legacy list/dict**: A list of per-agent dicts (or a single
          dict) each containing a ``reviewer`` field.

        Fault-tolerant: malformed agent responses are logged and skipped
        rather than raising. The agent name is added to the failed list.

        Args:
            response: Raw response from the RocketRide SDK.

        Returns:
            A tuple of (valid AgentReview objects, names of failed agents).

        Raises:
            PipelineError: If the top-level response structure is
                unexpected (not a dict or list).
        """
        # Detect named-lane response format
        if isinstance(response, dict) and set(response.keys()) <= set(
            LANE_TO_REVIEWER.keys()
        ):
            return self._parse_lane_response(response)

        if isinstance(response, dict):
            results = [response]
        elif isinstance(response, list):
            results = response
        else:
            msg = f"Unexpected pipeline response type: {type(response).__name__}"
            raise PipelineError(msg)

        reviews: list[AgentReview] = []
        failed_agents: list[str] = []

        for result in results:
            if not isinstance(result, dict):
                logger.warning(
                    "Expected dict in pipeline results, got %s — skipping",
                    type(result).__name__,
                )
                failed_agents.append("unknown")
                continue

            reviewer_name = str(result.get("reviewer", "unknown"))
            try:
                review = AgentReview(**result)
            except (ValidationError, TypeError) as e:
                logger.warning(
                    "Invalid response from agent %s: %s — skipping",
                    reviewer_name,
                    e,
                )
                failed_agents.append(reviewer_name)
                continue

            reviews.append(review)

        return reviews, failed_agents

    def _parse_lane_response(
        self, response: dict[str, object]
    ) -> tuple[list[AgentReview], list[str]]:
        """Parse a named-lane response dict into AgentReview objects.

        Each key in the response corresponds to a lane name from
        ``LANE_TO_REVIEWER``. The reviewer name is injected from the
        mapping so pipeline JSON does not need to include it.

        Args:
            response: Dict keyed by lane names (e.g. ``"claude"``,
                ``"openai"``, ``"gemini"``).

        Returns:
            A tuple of (valid AgentReview objects, names of failed agents).
        """
        reviews: list[AgentReview] = []
        failed_agents: list[str] = []

        for lane_name, lane_data in response.items():
            reviewer_name = LANE_TO_REVIEWER.get(lane_name, lane_name)

            if not isinstance(lane_data, dict):
                logger.warning(
                    "Expected dict for lane %s, got %s — skipping",
                    lane_name,
                    type(lane_data).__name__,
                )
                failed_agents.append(reviewer_name)
                continue

            lane_data_with_reviewer = {**lane_data, "reviewer": reviewer_name}
            try:
                review = AgentReview(**lane_data_with_reviewer)
            except (ValidationError, TypeError) as e:
                logger.warning(
                    "Invalid response from lane %s (%s): %s — skipping",
                    lane_name,
                    reviewer_name,
                    e,
                )
                failed_agents.append(reviewer_name)
                continue

            reviews.append(review)

        return reviews, failed_agents

    async def run_conversation_reply(
        self,
        agent_node_id: str,
        thread_context: str,
        file_context: str = "",
    ) -> str:
        """Run the single-agent conversation reply pipeline.

        Loads the per-agent conversation reply pipeline file, sends thread
        context and optional file context, and returns the agent's reply.

        Args:
            agent_node_id: The RocketRide node ID of the responding agent
                (e.g., ``"claude-reviewer"``).
            thread_context: Formatted conversation thread text.
            file_context: Optional surrounding code context.

        Returns:
            The reply text from the agent.

        Raises:
            PipelineError: If the agent is unknown, the pipeline file is
                missing, or execution fails.
        """
        pipeline_filename = CONVERSATION_PIPELINE_FILES.get(agent_node_id)
        if pipeline_filename is None:
            msg = f"Unknown agent node ID for conversation reply: {agent_node_id}"
            raise PipelineError(msg)

        pipeline_path = self._pipeline_dir / pipeline_filename
        if not pipeline_path.is_file():
            msg = f"Pipeline file not found: {pipeline_path}"
            raise PipelineError(msg)

        pipeline_data = json.loads(pipeline_path.read_text(encoding="utf-8"))
        self._inject_api_keys(pipeline_data)

        input_data: dict[str, str] = {
            "thread_context": thread_context,
            "agent_node_id": agent_node_id,
        }
        if file_context:
            input_data["file_context"] = file_context

        raw_status = await self._execute_pipeline(
            pipeline_data, input_data, "Conversation reply pipeline failed"
        )
        logger.info(
            "Conversation pipeline raw status: %s",
            json.dumps(raw_status, default=str)[:2000],
        )
        response = self._strip_status_metadata(raw_status)
        logger.info(
            "Conversation pipeline response (stripped): %s",
            json.dumps(response, default=str)[:2000],
        )

        return self._extract_reply(response)

    def _extract_reply(self, response: object) -> str:
        """Extract the reply text from a conversation pipeline response.

        Args:
            response: Raw response from the RocketRide SDK.

        Returns:
            The reply string.

        Raises:
            PipelineError: If the response structure is unexpected or
                the reply field is missing.
        """
        if not isinstance(response, dict):
            msg = (
                f"Unexpected conversation response type: " f"{type(response).__name__}"
            )
            raise PipelineError(msg)

        reply = response.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            msg = "Conversation response missing 'reply' field or reply is empty"
            raise PipelineError(msg)

        return reply.strip()
