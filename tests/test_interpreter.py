"""GroqInterpreter tests with a fake Groq client (no network, no API key)."""

import json
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from accessible_geometry.conversation import Exchange
from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import (
    TOOL_NAME,
    CreateCircle,
    CreatePoint,
    CreateSegment,
)
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.llm.interpreter import MAX_ATTEMPTS, GroqInterpreter
from accessible_geometry.llm.prompts import build_system_prompt

_ids = count()


def apply_actions(*actions: dict[str, Any], tool: str = TOOL_NAME) -> SimpleNamespace:
    """A fake `apply_actions` tool call."""
    arguments = json.dumps({"actions": list(actions)})
    return SimpleNamespace(
        id=f"call_{next(_ids)}", function=SimpleNamespace(name=tool, arguments=arguments)
    )


class FakeGroqClient:
    """Answers each chat completion with the next scripted list of tool calls.

    A response of `None` is a plain text answer without any tool call.
    """

    def __init__(self, *responses: list[SimpleNamespace] | None) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot the messages: the interpreter keeps appending to the same list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        tool_calls = self.responses.pop(0)
        message = SimpleNamespace(tool_calls=tool_calls, content=None if tool_calls else "Hello")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def make_interpreter(client: FakeGroqClient) -> GroqInterpreter:
    return GroqInterpreter(client, model="test-model")  # type: ignore[arg-type]


async def test_whole_request_in_one_llm_call(triangle_points: ConstructionState) -> None:
    client = FakeGroqClient(
        [
            apply_actions(
                {"action": "create_point", "name": "O"},
                {"action": "create_circle", "center": "O", "radius": 3},
            )
        ]
    )
    actions = await make_interpreter(client).interpret(
        "cercle de centre O et de rayon 3", triangle_points, "fr", []
    )

    assert actions == [CreatePoint(name="O"), CreateCircle(center="O", radius=3)]
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request["model"] == "test-model"
    assert request["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in request["tools"]] == [TOOL_NAME]
    assert request["messages"][-1] == {
        "role": "user",
        "content": "cercle de centre O et de rayon 3",
    }
    assert "- A: point at (0, 0)" in request["messages"][0]["content"]


async def test_split_calls_are_concatenated() -> None:
    client = FakeGroqClient(
        [
            apply_actions({"action": "create_point", "name": "A"}),
            apply_actions({"action": "create_point", "name": "B"}),
        ]
    )
    actions = await make_interpreter(client).interpret("A et B", ConstructionState(), "fr", [])
    assert actions == [CreatePoint(name="A"), CreatePoint(name="B")]


async def test_invalid_call_is_sent_back_for_correction() -> None:
    bad = apply_actions({"action": "create_segment", "start": "A", "end": "A"})
    client = FakeGroqClient(
        [bad], [apply_actions({"action": "create_segment", "start": "A", "end": "B"})]
    )
    actions = await make_interpreter(client).interpret("segment AB", ConstructionState(), "fr", [])

    assert actions == [CreateSegment(start="A", end="B")]
    assert len(client.requests) == 2
    assistant, tool_result, reminder = client.requests[1]["messages"][-3:]
    assert assistant["tool_calls"][0]["id"] == bad.id
    assert tool_result["tool_call_id"] == bad.id
    assert tool_result["content"].startswith("Error: action 1: invalid create_segment")
    assert reminder["role"] == "user"


async def test_gives_up_after_max_attempts() -> None:
    bad = [apply_actions({"action": "rm_rf"})]
    client = FakeGroqClient(*([bad] * MAX_ATTEMPTS))
    with pytest.raises(InterpretationError):
        await make_interpreter(client).interpret("rm", ConstructionState(), "fr", [])
    assert len(client.requests) == MAX_ATTEMPTS


async def test_history_is_sent_before_the_new_message() -> None:
    client = FakeGroqClient([apply_actions({"action": "create_point", "name": "B"})])
    history = [Exchange(user="place le point A", assistant="Point A placé en (0 ; 0).")]
    await make_interpreter(client).interpret("non, B", ConstructionState(), "fr", history)

    roles_and_contents = [(m["role"], m["content"]) for m in client.requests[0]["messages"][1:]]
    assert roles_and_contents == [
        ("user", "place le point A"),
        ("assistant", "Point A placé en (0 ; 0)."),
        ("user", "non, B"),
    ]


async def test_no_tool_call_is_an_interpretation_error() -> None:
    with pytest.raises(InterpretationError):
        await make_interpreter(FakeGroqClient(None)).interpret(
            "bonjour", ConstructionState(), "fr", []
        )


def test_prompt_describes_figure_and_language(triangle_points: ConstructionState) -> None:
    prompt = build_system_prompt("en", triangle_points)
    assert "speaks English" in prompt
    assert "- f: segment, defined as Segment(A, B), value 4" in prompt
    assert "(empty)" in build_system_prompt("fr", ConstructionState())
