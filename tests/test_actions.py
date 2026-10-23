import json

import pytest
from pydantic import ValidationError

from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import (
    ACTION_TYPES,
    MAX_ACTIONS,
    TOOL_NAME,
    AskClarification,
    CreateCircle,
    CreatePoint,
    CreateSegment,
    parse_tool_call,
    tool_definitions,
)


class TestValidation:
    def test_point_needs_both_coordinates_or_none(self) -> None:
        assert CreatePoint(name="A").x is None
        assert CreatePoint(name="A", x=1, y=2).y == 2
        with pytest.raises(ValidationError):
            CreatePoint(name="A", x=1)

    @pytest.mark.parametrize("name", ["A", "B1", "A'", "A_1", "d"])
    def test_valid_names(self, name: str) -> None:
        assert CreatePoint(name=name).name == name

    @pytest.mark.parametrize("name", ["", "1A", "A B", "A;Delete(B)", "A" * 20])
    def test_invalid_names_are_rejected(self, name: str) -> None:
        with pytest.raises(ValidationError):
            CreatePoint(name=name)

    def test_coordinates_are_bounded(self) -> None:
        with pytest.raises(ValidationError):
            CreatePoint(x=1e9, y=0)

    def test_segment_needs_two_distinct_points(self) -> None:
        with pytest.raises(ValidationError):
            CreateSegment(start="A", end="A")

    def test_circle_needs_exactly_one_of_radius_and_through(self) -> None:
        CreateCircle(center="O", radius=3)
        CreateCircle(center="O", through="A")
        with pytest.raises(ValidationError):
            CreateCircle(center="O")
        with pytest.raises(ValidationError):
            CreateCircle(center="O", radius=3, through="A")

    def test_circle_radius_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            CreateCircle(center="O", radius=0)


def call(*actions: dict[str, object]) -> str:
    return json.dumps({"actions": list(actions)})


class TestParseToolCall:
    def test_parses_actions_in_order(self) -> None:
        actions = parse_tool_call(
            TOOL_NAME,
            call(
                {"action": "create_point", "name": "O"},
                {"action": "create_circle", "center": "O", "radius": 3},
            ),
        )
        assert actions == [CreatePoint(name="O"), CreateCircle(center="O", radius=3)]

    def test_tolerates_extra_arguments(self) -> None:
        actions = parse_tool_call(TOOL_NAME, call({"action": "create_point", "color": "red"}))
        assert actions == [CreatePoint()]

    def test_unknown_tool(self) -> None:
        with pytest.raises(InterpretationError, match="unknown tool"):
            parse_tool_call("create_point", call({"action": "create_point"}))

    def test_unknown_action(self) -> None:
        with pytest.raises(InterpretationError, match="unknown action 'rm_rf'"):
            parse_tool_call(TOOL_NAME, call({"action": "rm_rf"}))

    def test_errors_name_every_faulty_item(self) -> None:
        with pytest.raises(InterpretationError) as info:
            parse_tool_call(
                TOOL_NAME,
                call(
                    {"action": "create_segment", "start": "A"},
                    {"action": "create_point", "name": "B"},
                    {"action": "create_circle", "center": "O"},
                ),
            )
        message = str(info.value)
        assert "action 1: invalid create_segment (end: Field required)" in message
        assert "action 2" not in message
        assert "action 3: invalid create_circle" in message

    @pytest.mark.parametrize(
        "arguments",
        ["{not json", "[]", "{}", '{"actions": []}', '{"actions": "point"}', '{"actions": [1]}'],
    )
    def test_malformed_arguments(self, arguments: str) -> None:
        with pytest.raises(InterpretationError):
            parse_tool_call(TOOL_NAME, arguments)

    def test_number_of_actions_is_limited(self) -> None:
        with pytest.raises(InterpretationError, match="at most"):
            parse_tool_call(TOOL_NAME, call(*[{"action": "undo"}] * (MAX_ACTIONS + 1)))


class TestToolDefinitions:
    def _item_schemas(self) -> dict[str, dict[str, object]]:
        (tool,) = tool_definitions()
        items = tool["function"]["parameters"]["properties"]["actions"]["items"]["anyOf"]
        return {item["properties"]["action"]["const"]: item for item in items}

    def test_single_tool_listing_every_action(self) -> None:
        (tool,) = tool_definitions()
        assert tool["function"]["name"] == TOOL_NAME
        assert list(self._item_schemas()) == [action.action_name for action in ACTION_TYPES]

    def test_schemas_are_simplified(self) -> None:
        text = json.dumps(tool_definitions())
        assert '"title"' not in text
        assert '"null"' not in text
        assert "$ref" not in text
        for keyword in ("pattern", "default", "minimum", "maximum"):
            assert f'"{keyword}"' not in text

    def test_constraints_dropped_from_schema_are_still_enforced(self) -> None:
        with pytest.raises(InterpretationError, match="name"):
            parse_tool_call(TOOL_NAME, call({"action": "create_point", "name": "A;Delete(B)"}))
        with pytest.raises(InterpretationError, match="radius"):
            parse_tool_call(
                TOOL_NAME, call({"action": "create_circle", "center": "O", "radius": -1})
            )

    def test_only_mandatory_parameters_are_required(self) -> None:
        schemas = self._item_schemas()
        assert schemas["create_point"]["required"] == ["action"]
        assert schemas["create_segment"]["required"] == ["action", "start", "end"]
        assert schemas["create_point"]["properties"]["x"]["type"] == "number"  # type: ignore[index]

    def test_every_action_has_a_description(self) -> None:
        assert all(schema["description"] for schema in self._item_schemas().values())

    def test_clarification_round_trip(self) -> None:
        actions = parse_tool_call(
            TOOL_NAME, call({"action": "ask_clarification", "question": "Quel point ?"})
        )
        assert actions == [AskClarification(question="Quel point ?")]
