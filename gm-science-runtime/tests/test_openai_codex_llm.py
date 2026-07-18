"""Tests for OpenAI Codex ADK adapter."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from pydantic import BaseModel

from openppx.core.openai_codex_llm import (
    OpenAICodexLlm,
    _consume_codex_events,
    _convert_llm_request,
    _stream_codex_with_retries,
)


class OpenAICodexLlmTests(unittest.TestCase):
    def test_generate_content_async_maps_response_schema_to_codex_text_format(self) -> None:
        """ADK structured output should use the Responses API JSON schema field."""

        class ReviewResult(BaseModel):
            verdict: str
            findings: list[str]

        llm = OpenAICodexLlm(model="openai-codex/gpt-5.5")
        llm_request = LlmRequest(
            model="openai-codex/gpt-5.5",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text="Review this")])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReviewResult,
            ),
        )
        fake_token = type("Token", (), {"account_id": "acc_1", "access": "tok_1"})()
        request_mock = AsyncMock(return_value=('{"verdict":"clean","findings":[]}', [], types.FinishReason.STOP))

        with patch("openppx.core.openai_codex_llm._get_codex_token", return_value=fake_token):
            with patch("openppx.core.openai_codex_llm._request_codex", new=request_mock):
                async def _collect():
                    return [event async for event in llm.generate_content_async(llm_request, stream=False)]

                asyncio.run(_collect())

        text_config = request_mock.await_args.kwargs["body"]["text"]
        self.assertEqual(text_config["verbosity"], "medium")
        self.assertEqual(text_config["format"]["type"], "json_schema")
        self.assertEqual(text_config["format"]["name"], "ReviewResult")
        self.assertTrue(text_config["format"]["strict"])
        schema = text_config["format"]["schema"]
        self.assertEqual(schema["required"], ["verdict", "findings"])
        self.assertFalse(schema["additionalProperties"])

    def test_convert_llm_request_with_tools_and_tool_outputs(self) -> None:
        """Adapter should map ADK content stream into Codex input items."""
        assistant_call = types.Part.from_function_call(name="search_docs", args={"q": "oauth"})
        assistant_call.function_call.id = "call_123"
        tool_output = types.Part.from_function_response(
            name="search_docs",
            response={"ok": True, "hits": 2},
        )
        tool_output.function_response.id = "call_123"

        llm_request = LlmRequest(
            model="openai-codex/gpt-5.5",
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text="Find OAuth docs")]),
                types.Content(role="model", parts=[assistant_call]),
                types.Content(role="tool", parts=[tool_output]),
            ],
            config=types.GenerateContentConfig(
                system_instruction="You are helpful.",
                tools=[
                    types.Tool(
                        function_declarations=[
                            types.FunctionDeclaration(
                                name="search_docs",
                                description="Search docs",
                                parameters_json_schema={
                                    "type": "object",
                                    "properties": {"q": {"type": "string"}},
                                    "required": ["q"],
                                },
                            )
                        ]
                    )
                ],
            ),
        )

        instructions, input_items, tools = _convert_llm_request(llm_request)

        self.assertEqual(instructions, "You are helpful.")
        self.assertEqual(input_items[0]["role"], "user")
        self.assertIn("input_text", str(input_items[0]["content"]))
        self.assertEqual(input_items[1]["type"], "function_call")
        self.assertEqual(input_items[1]["call_id"], "call_123")
        self.assertEqual(input_items[2]["type"], "function_call_output")
        self.assertEqual(input_items[2]["call_id"], "call_123")
        self.assertEqual(tools[0]["name"], "search_docs")

    def test_consume_codex_events_extracts_text_and_function_calls(self) -> None:
        """SSE event reducer should produce final text, calls and finish reason."""
        events = [
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "id": "fc_1",
                    "name": "search_docs",
                    "arguments": "",
                },
            },
            {"type": "response.output_text.delta", "delta": "hello "},
            {"type": "response.function_call_arguments.delta", "call_id": "call_1", "delta": '{"q":"oauth'},
            {"type": "response.function_call_arguments.delta", "call_id": "call_1", "delta": ' docs"}'},
            {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "call_id": "call_1"},
            },
            {
                "type": "response.completed",
                "response": {"status": "completed"},
            },
        ]
        text, tool_calls, finish_reason = _consume_codex_events(events)
        self.assertEqual(text, "hello ")
        self.assertEqual(finish_reason, types.FinishReason.STOP)
        self.assertEqual(tool_calls[0].id, "call_1")
        self.assertEqual(tool_calls[0].name, "search_docs")
        self.assertEqual(tool_calls[0].arguments, {"q": "oauth docs"})

    def test_generate_content_async_success_path(self) -> None:
        """Adapter should emit one final ADK response object on successful call."""
        llm = OpenAICodexLlm(model="openai-codex/gpt-5.5")
        llm_request = LlmRequest(
            model="openai-codex/gpt-5.5",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text="hello")])],
            config=types.GenerateContentConfig(system_instruction="system"),
        )

        fake_token = type("Token", (), {"account_id": "acc_1", "access": "tok_1"})()
        request_mock = AsyncMock(return_value=("hello world", [], types.FinishReason.STOP))
        with patch("openppx.core.openai_codex_llm._get_codex_token", return_value=fake_token):
            with patch("openppx.core.openai_codex_llm._request_codex", new=request_mock):
                async def _collect():
                    return [event async for event in llm.generate_content_async(llm_request, stream=False)]

                events = asyncio.run(_collect())

        request_body = request_mock.await_args.kwargs["body"]
        self.assertEqual(request_body["model"], "gpt-5.5")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].finish_reason, types.FinishReason.STOP)
        self.assertIsNotNone(events[0].content)
        self.assertEqual(events[0].content.parts[0].text, "hello world")

    def test_generate_content_async_streams_partial_chunks_and_one_complete_final(self) -> None:
        """Codex SSE text should cross the adapter as native ADK partial responses."""
        llm = OpenAICodexLlm(model="openai-codex/gpt-5.5")
        llm_request = LlmRequest(
            model="openai-codex/gpt-5.5",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text="hello")])],
            config=types.GenerateContentConfig(system_instruction="system"),
        )

        async def _stream_mock(**_kwargs):
            yield {"type": "response.output_text.delta", "delta": "hello "}
            yield {"type": "response.output_text.delta", "delta": "world"}
            yield {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "id": "fc_1",
                    "name": "search_docs",
                    "arguments": "",
                },
            }
            yield {
                "type": "response.function_call_arguments.done",
                "call_id": "call_1",
                "arguments": '{"q":"streaming"}',
            }
            yield {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "call_id": "call_1"},
            }
            yield {"type": "response.completed", "response": {"status": "completed"}}

        fake_token = type("Token", (), {"account_id": "acc_1", "access": "tok_1"})()
        with patch("openppx.core.openai_codex_llm._get_codex_token", return_value=fake_token):
            with patch("openppx.core.openai_codex_llm._stream_codex_with_retries", new=_stream_mock):
                async def _collect():
                    return [event async for event in llm.generate_content_async(llm_request, stream=True)]

                events = asyncio.run(_collect())

        self.assertGreaterEqual(len(events), 4)
        self.assertTrue(all(event.partial for event in events[:-1]))
        self.assertTrue(all(event.turn_complete is False for event in events[:-1]))
        self.assertEqual(
            [event.content.parts[0].text for event in events[:2]],
            ["hello ", "world"],
        )
        self.assertFalse(events[-1].partial)
        self.assertTrue(events[-1].turn_complete)
        self.assertEqual(events[-1].content.parts[0].text, "hello world")
        self.assertEqual(events[-1].content.parts[1].function_call.name, "search_docs")
        self.assertEqual(events[-1].content.parts[1].function_call.args, {"q": "streaming"})

    def test_generate_content_async_retries_transient_codex_transport_error(self) -> None:
        """Transient stream disconnects should retry before surfacing an error event."""
        llm = OpenAICodexLlm(model="openai-codex/gpt-5.5")
        llm_request = LlmRequest(
            model="openai-codex/gpt-5.5",
            contents=[types.Content(role="user", parts=[types.Part.from_text(text="hello")])],
            config=types.GenerateContentConfig(system_instruction="system"),
        )

        request_mock = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
                ("retry ok", [], types.FinishReason.STOP),
            ]
        )
        fake_token = type("Token", (), {"account_id": "acc_1", "access": "tok_1"})()
        with patch("openppx.core.openai_codex_llm._get_codex_token", return_value=fake_token):
            with patch("openppx.core.openai_codex_llm._request_codex", new=request_mock):
                with patch("openppx.core.openai_codex_llm.asyncio.sleep", new=AsyncMock()):
                    async def _collect():
                        return [event async for event in llm.generate_content_async(llm_request, stream=False)]

                    events = asyncio.run(_collect())

        self.assertEqual(request_mock.await_count, 2)
        self.assertEqual(events[0].content.parts[0].text, "retry ok")
        self.assertFalse(getattr(events[0], "error_code", None))

    def test_stream_retries_transport_failure_before_content(self) -> None:
        """A disconnected SSE request may retry before any response content appears."""
        attempts = 0

        async def _stream_mock(**_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.RemoteProtocolError("peer closed connection")
            yield {"type": "response.output_text.delta", "delta": "recovered"}

        with patch("openppx.core.openai_codex_llm._stream_codex", new=_stream_mock):
            with patch("openppx.core.openai_codex_llm.asyncio.sleep", new=AsyncMock()):
                async def _collect():
                    return [
                        event
                        async for event in _stream_codex_with_retries(
                            url="https://example.test/responses",
                            headers={},
                            body={},
                            timeout_seconds=1,
                            verify=True,
                        )
                    ]

                events = asyncio.run(_collect())

        self.assertEqual(attempts, 2)
        self.assertEqual(events[0]["delta"], "recovered")

    def test_stream_does_not_retry_after_content_starts(self) -> None:
        """Retry must not duplicate partial text already delivered to ADK."""
        attempts = 0
        observed: list[dict[str, object]] = []

        async def _stream_mock(**_kwargs):
            nonlocal attempts
            attempts += 1
            yield {"type": "response.output_text.delta", "delta": "visible"}
            raise httpx.RemoteProtocolError("peer closed connection")

        async def _collect() -> None:
            async for event in _stream_codex_with_retries(
                url="https://example.test/responses",
                headers={},
                body={},
                timeout_seconds=1,
                verify=True,
            ):
                observed.append(event)

        with patch("openppx.core.openai_codex_llm._stream_codex", new=_stream_mock):
            with self.assertRaises(httpx.RemoteProtocolError):
                asyncio.run(_collect())

        self.assertEqual(attempts, 1)
        self.assertEqual(observed[0]["delta"], "visible")


if __name__ == "__main__":
    unittest.main()
