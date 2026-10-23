"""GroqInterpreter tests with a fake Groq client (no network, no API key)."""

from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from accessible_geometry.conversation import Exchange
from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import (
    AskClarification,
    CreateCircle,
    CreatePoint,
    CreateSegment,
)
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.llm.interpreter import MAX_ROUNDS, GroqInterpreter
from accessible_geometry.llm.prompts import build_system_prompt

_ids = count()


def tool_call(name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call_{next(_ids)}", function=SimpleNamespace(name=name, arguments=arguments)
    )


class FakeGroqClient:
    """Answers each chat completion with the next scripted round of tool calls.

    A round of `None` is a plain text answer (the model is done). After the
    script runs out, the model keeps answering with text.
    """

    def __init__(self, *rounds: list[SimpleNamespace] | None) -> None:
        self.rounds = list(rounds)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot the messages: the interpreter keeps appending to the same list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        tool_calls = self.rounds.pop(0) if self.rounds else None
        message = SimpleNamespace(tool_calls=tool_calls, content=None if tool_calls else "Done.")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def make_interpreter(client: FakeGroqClient) -> GroqInterpreter:
    return GroqInterpreter(client, model="test-model")  # type: ignore[arg-type]


async def test_collects_tool_calls_across_rounds() -> None:
    # The model emits one call per response, as gpt-oss does on Groq.
    client = FakeGroqClient(
        [tool_call("create_point", '{"name": "O"}')],
        [tool_call("create_circle", '{"center": "O", "radius": 3}')],
        None,
    )
    actions = await make_interpreter(client).interpret(
        "cercle de centre O et de rayon 3", ConstructionState(), "fr", []
    )

    assert actions == [CreatePoint(name="O"), CreateCircle(center="O", radius=3)]
    assert len(client.requests) == 3
    assert client.requests[0]["tool_choice"] == "required"
    assert client.requests[1]["tool_choice"] == "auto"
    # The second request carries the first call and its result.
    assistant, tool_result = client.requests[1]["messages"][-2:]
    assert assistant["tool_calls"][0]["function"]["name"] == "create_point"
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == assistant["tool_calls"][0]["id"]


async def test_several_calls_in_one_round(triangle_points: ConstructionState) -> None:
    client = FakeGroqClient(
        [
            tool_call("create_point", '{"name": "D", "x": 2, "y": 2}'),
            tool_call("create_segment", '{"start": "A", "end": "D"}'),
        ],
    )
    actions = await make_interpreter(client).interpret("place D en 2 2", triangle_points, "fr", [])

    assert actions == [CreatePoint(name="D", x=2, y=2), CreateSegment(start="A", end="D")]
    request = client.requests[0]
    assert request["model"] == "test-model"
    assert request["messages"][-1] == {"role": "user", "content": "place D en 2 2"}
    assert "- A: point at (0, 0)" in request["messages"][0]["content"]


async def test_invalid_call_is_sent_back_for_correction() -> None:
    client = FakeGroqClient(
        [tool_call("create_segment", '{"start": "A", "end": "A"}')],
        [tool_call("create_segment", '{"start": "A", "end": "B"}')],
    )
    actions = await make_interpreter(client).interpret("segment AB", ConstructionState(), "fr", [])

    assert actions == [CreateSegment(start="A", end="B")]
    assert client.requests[1]["messages"][-1]["content"].startswith("Error:")


async def test_clarification_stops_the_loop() -> None:
    client = FakeGroqClient(
        [tool_call("ask_clarification", '{"question": "Quel point ?"}')],
        [tool_call("create_point", "{}")],
    )
    actions = await make_interpreter(client).interpret("trace", ConstructionState(), "fr", [])

    assert actions == [AskClarification(question="Quel point ?")]
    assert len(client.requests) == 1


async def test_loop_is_bounded() -> None:
    client = FakeGroqClient(*([tool_call("create_point", "{}")] for _ in range(MAX_ROUNDS + 5)))
    actions = await make_interpreter(client).interpret("points", ConstructionState(), "fr", [])
    assert len(actions) == MAX_ROUNDS


async def test_history_is_sent_before_the_new_message() -> None:
    client = FakeGroqClient([tool_call("create_point", '{"name": "B"}')])
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


async def test_only_invalid_calls_is_an_interpretation_error() -> None:
    client = FakeGroqClient([tool_call("create_segment", '{"start": "A", "end": "A"}')])
    with pytest.raises(InterpretationError):
        await make_interpreter(client).interpret("segment AA", ConstructionState(), "fr", [])


def test_prompt_describes_figure_and_language(triangle_points: ConstructionState) -> None:
    prompt = build_system_prompt("en", triangle_points)
    assert "speaks English" in prompt
    assert "- f: segment, defined as Segment(A, B), value 4" in prompt
    assert "(empty)" in build_system_prompt("fr", ConstructionState())
