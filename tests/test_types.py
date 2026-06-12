from __future__ import annotations

from pilot_agent.agent.types import (
    CompletionResponse,
    Message,
    Role,
    ToolCall,
    ToolResult,
    from_json,
    to_json,
)


def test_assistant_message_round_trip_content_and_tool_calls() -> None:
    msg = Message(
        role=Role.ASSISTANT,
        content="I will inspect the file.",
        tool_calls=[ToolCall(id="call_1", name="read_file", arguments={"path": "README.md"})],
        phase="coding",
    )

    decoded = from_json(to_json(msg))

    assert decoded == msg


def test_tool_message_round_trip_multiple_results() -> None:
    msg = Message(
        role=Role.TOOL,
        tool_results=[
            ToolResult(
                tool_call_id="call_1",
                content="ok",
                artifact_path=".pilot-agent/artifacts/1.txt",
            ),
            ToolResult(tool_call_id="call_2", content="bad", is_error=True, truncated=True),
        ],
    )

    decoded = from_json(to_json(msg))

    assert decoded == msg


def test_completion_response_round_trip() -> None:
    response = CompletionResponse(
        message=Message(role=Role.ASSISTANT, content="done"),
        stop_reason="end_turn",
        usage={"input_tokens": 1, "output_tokens": 2},
    )

    decoded = from_json(to_json(response))

    assert decoded == response
