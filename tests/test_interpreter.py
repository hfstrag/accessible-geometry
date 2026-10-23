"""GroqInterpreter tests with a fake Groq client (no network, no API key)."""

from types import SimpleNamespace
from typing import Any

import pytest

from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import CreatePoint, CreateSegment
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.llm.interpreter import GroqInterpreter
from accessible_geometry.llm.prompts import build_system_prompt


def tool_call(name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class FakeGroqClient:
    def __init__(self, tool_calls: list[SimpleNamespace] | None) -> None:
        self.requests: list[dict[str, Any]] = []
        message = SimpleNamespace(tool_calls=tool_calls, content=None)
        self._response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return self._response


def make_interpreter(client: FakeGroqClient) -> GroqInterpreter:
    return GroqInterpreter(client, model="test-model")  # type: ignore[arg-type]


async def test_parses_tool_calls_in_order(triangle_points: ConstructionState) -> None:
    client = FakeGroqClient(
        [
            tool_call("create_point", '{"name": "D", "x": 2, "y": 2}'),
            tool_call("create_segment", '{"start": "A", "end": "D"}'),
        ]
    )
    actions = await make_interpreter(client).interpret("place D en 2 2", triangle_points, "fr")

    assert actions == [CreatePoint(name="D", x=2, y=2), CreateSegment(start="A", end="D")]
    request = client.requests[0]
    assert request["model"] == "test-model"
    assert request["tool_choice"] == "required"
    assert request["messages"][1] == {"role": "user", "content": "place D en 2 2"}
    assert "- A: point at (0, 0)" in request["messages"][0]["content"]


async def test_no_tool_call_is_an_interpretation_error() -> None:
    with pytest.raises(InterpretationError):
        await make_interpreter(FakeGroqClient(None)).interpret("bonjour", ConstructionState(), "fr")


async def test_invalid_tool_call_is_an_interpretation_error() -> None:
    client = FakeGroqClient([tool_call("create_segment", '{"start": "A", "end": "A"}')])
    with pytest.raises(InterpretationError):
        await make_interpreter(client).interpret("segment AA", ConstructionState(), "fr")


def test_prompt_describes_figure_and_language(triangle_points: ConstructionState) -> None:
    prompt = build_system_prompt("en", triangle_points)
    assert "speaks English" in prompt
    assert "- f: segment, defined as Segment(A, B), value 4" in prompt
    assert "(empty)" in build_system_prompt("fr", ConstructionState())
