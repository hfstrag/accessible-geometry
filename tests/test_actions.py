import json

import pytest
from pydantic import ValidationError

from accessible_geometry.errors import InterpretationError
from accessible_geometry.geometry.actions import (
    ACTION_TYPES,
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


class TestParseToolCall:
    def test_parses_valid_call(self) -> None:
        action = parse_tool_call("create_segment", '{"start": "A", "end": "B"}')
        assert action == CreateSegment(start="A", end="B")

    def test_tolerates_extra_arguments(self) -> None:
        action = parse_tool_call("create_point", '{"name": "A", "color": "red"}')
        assert action == CreatePoint(name="A")

    def test_unknown_tool(self) -> None:
        with pytest.raises(InterpretationError):
            parse_tool_call("rm_rf", "{}")

    def test_invalid_arguments(self) -> None:
        with pytest.raises(InterpretationError):
            parse_tool_call("create_segment", '{"start": "A"}')

    def test_malformed_json(self) -> None:
        with pytest.raises(InterpretationError):
            parse_tool_call("create_segment", "{not json")


class TestToolDefinitions:
    def test_one_tool_per_action(self) -> None:
        names = [tool["function"]["name"] for tool in tool_definitions()]
        assert names == [action.tool_name for action in ACTION_TYPES]

    def test_schemas_are_simplified(self) -> None:
        text = json.dumps(tool_definitions())
        assert '"title"' not in text
        assert '"null"' not in text

    def test_optional_parameters_are_not_required(self) -> None:
        (point_tool,) = [t for t in tool_definitions() if t["function"]["name"] == "create_point"]
        parameters = point_tool["function"]["parameters"]
        assert parameters.get("required", []) == []
        assert parameters["properties"]["x"]["type"] == "number"

    def test_every_tool_has_a_description(self) -> None:
        assert all(tool["function"]["description"] for tool in tool_definitions())
