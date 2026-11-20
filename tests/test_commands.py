"""Whitelisted GeoGebra commands, renaming and moving points (milestone 2)."""

import pytest
from pydantic import ValidationError

from accessible_geometry.errors import PlanningError
from accessible_geometry.geometry.actions import (
    CreateLine,
    CreatePoint,
    GeoGebraCommand,
    GeometryAction,
    MovePoint,
    RenameObject,
    tool_definitions,
)
from accessible_geometry.geometry.commands import COMMANDS
from accessible_geometry.geometry.planner import EvalStep, Plan, plan_actions
from accessible_geometry.geometry.state import ConstructionState, GeoObject
from accessible_geometry.i18n import translate


def _point(name: str, x: float, y: float, definition: str = "") -> GeoObject:
    return GeoObject(name=name, type="point", definition=definition, x=x, y=y)


FIGURE = ConstructionState(
    objects=[
        _point("A", 0, 0),
        _point("B", 4, 0),
        _point("C", 0, 3),
        _point("I", 2, 0, definition="Midpoint(A, B)"),
        GeoObject(name="f", type="line", definition="Line(A, B)"),
        GeoObject(name="g", type="segment", definition="Segment(B, C)", value="5"),
        GeoObject(name="c", type="circle", definition="Circle(A, 2)"),
        GeoObject(name="t1", type="triangle", definition="Polygon(A, B, C)", value="6"),
    ]
)


def cmd(command: str, *args: str | float, name: str | None = None) -> GeoGebraCommand:
    return GeoGebraCommand(command=command, args=list(args), name=name)


def plan(*actions: GeometryAction, language: str = "fr") -> Plan:
    return plan_actions(list(actions), FIGURE, language)  # type: ignore[arg-type]


def commands(result: Plan) -> list[str]:
    return [step.command for step in result.steps if isinstance(step, EvalStep)]


class TestValidation:
    def test_numbers_may_come_as_strings(self) -> None:
        assert cmd("Rotate", "A", "90", "O").args == ["A", 90.0, "O"]
        assert cmd("Rotate", "A", "-45,5", "O").args == ["A", -45.5, "O"]

    @pytest.mark.parametrize(
        "args",
        [("A",), ("A", "B", "C"), ("A", 3)],
    )
    def test_arguments_must_match_an_overload(self, args: tuple[str | float, ...]) -> None:
        with pytest.raises(ValidationError, match="Midpoint takes"):
            cmd("Midpoint", *args)

    def test_unknown_command(self) -> None:
        with pytest.raises(ValidationError):
            cmd("Execute", "A")

    def test_argument_names_are_checked(self) -> None:
        with pytest.raises(ValidationError):
            cmd("Midpoint", "A", "B);Delete(C")

    def test_schema_lists_every_command(self) -> None:
        (tool,) = tool_definitions()
        description = str(tool)
        for name in COMMANDS:
            assert f"{name}(" in description

    @pytest.mark.parametrize("language", ["fr", "en"])
    def test_every_overload_has_a_message(self, language: str) -> None:
        params = {f"a{i}": "x" for i in range(12)} | {"all": "x", "name": "x", "value": "1"}
        for overloads in COMMANDS.values():
            for overload in overloads:
                assert translate(overload.message, language, **params)  # type: ignore[arg-type]


class TestConstructions:
    def test_midpoint(self) -> None:
        result = plan(cmd("Midpoint", "A", "C", name="M"))
        assert result.steps == [EvalStep(command="M = Midpoint(A, C)", label="M")]
        assert result.message == "Milieu M de [AC] placé."

    def test_unnamed_point_gets_next_free_letter(self) -> None:
        assert commands(plan(cmd("Midpoint", "A", "C"))) == ["D = Midpoint(A, C)"]

    def test_perpendicular_uses_the_line_notation(self) -> None:
        result = plan(cmd("PerpendicularLine", "C", "f"))
        assert commands(result) == ["d = PerpendicularLine(C, f)"]
        assert result.message == "Perpendiculaire (d) à (AB) passant par C tracée."

    def test_parallel_to_a_segment_created_in_the_same_request(self) -> None:
        result = plan(
            CreatePoint(name="E", x=5, y=5),
            CreateLine(point1="A", point2="E", name="d"),
            cmd("ParallelLine", "B", "d"),
        )
        assert commands(result)[-1] == "d1 = Line(B, d)"
        assert result.messages[-1] == "Parallèle (d1) à (AE) passant par B tracée."

    def test_bisectors(self) -> None:
        assert plan(cmd("PerpendicularBisector", "A", "B")).message == (
            "Médiatrice (d) de [AB] tracée."
        )
        result = plan(cmd("AngleBisector", "B", "A", "C"), language="en")
        assert commands(result) == ["d = AngleBisector(B, A, C)"]
        assert result.message == "Bisector (d) of angle BAC drawn."

    def test_intersections(self) -> None:
        assert commands(plan(cmd("Intersect", "f", "g"))) == ["D = Intersect(f, g)"]
        assert commands(plan(cmd("Intersect", "c", "f", 2, name="E"))) == ["E = Intersect(c, f, 2)"]
        with pytest.raises(PlanningError, match="ne s'applique pas"):
            plan(cmd("Intersect", "c", "f"))  # a circle needs the index

    def test_polygon_reserves_side_names(self) -> None:
        result = plan(
            CreatePoint(name="D", x=-3, y=2),
            cmd("Polygon", "A", "B", "D"),
            cmd("PerpendicularLine", "C", "f"),
        )
        assert commands(result)[1:] == ["p1 = Polygon(A, B, D)", "d1 = PerpendicularLine(C, f)"]
        assert result.messages[1] == "Polygone ABD tracé."


class TestTransformations:
    def test_central_symmetry_names_the_image_with_a_prime(self) -> None:
        result = plan(cmd("Reflect", "B", "A"))
        assert result.steps == [EvalStep(command="B' = Reflect(B, A)", label="B'")]
        assert result.message == "B', symétrique de B par rapport au point A, construit."

    def test_axial_symmetry_of_a_polygon(self) -> None:
        result = plan(cmd("Reflect", "t1", "g"), language="en")
        assert commands(result) == ["t1' = Reflect(t1, g)"]
        assert result.message == "t1', reflection of ABC in the line [BC], drawn."

    def test_image_can_be_used_in_the_same_request(self) -> None:
        result = plan(cmd("Reflect", "A", "f"), cmd("Distance", "A", "A'"))
        assert commands(result)[1] == "m1 = Distance(A, A')"

    def test_translation_and_rotation(self) -> None:
        assert commands(plan(cmd("Translate", "C", "A", "B"))) == [
            "C' = Translate(C, Vector(A, B))"
        ]
        result = plan(cmd("Rotate", "c", -90, "B"))
        assert commands(result) == ["c' = Rotate(c, -90°, B)"]
        assert "rotation de centre B et d'angle -90°" in result.message

    def test_a_number_cannot_be_transformed(self) -> None:
        with pytest.raises(PlanningError):
            plan(cmd("Distance", "A", "B", name="m"), cmd("Reflect", "m", "A"))


class TestMeasures:
    def test_distance_leaves_a_placeholder_for_the_browser(self) -> None:
        result = plan(cmd("Distance", "A", "B"))
        assert commands(result) == ["m1 = Distance(A, B)"]
        assert result.message == "La longueur AB est {{m1}}."

    def test_angle_is_never_reflex(self) -> None:
        result = plan(cmd("Angle", "B", "A", "C"), language="en")
        assert commands(result) == [
            "m1 = If(Angle(B, A, C) <= 180°, Angle(B, A, C), Angle(C, A, B))"
        ]
        assert result.message == "Angle BAC measures {{m1}}°."

    def test_areas_and_perimeters(self) -> None:
        assert plan(cmd("Area", "t1")).message == "L'aire de ABC est {{m1}}."
        assert commands(plan(cmd("Area", "A", "B", "C"))) == ["m1 = Area(A, B, C)"]
        assert plan(cmd("Perimeter", "c"), language="en").message == (
            "The perimeter of c is {{m1}}."
        )

    def test_wrong_kind_of_argument(self) -> None:
        with pytest.raises(PlanningError, match="ne s'applique pas à A, f"):
            plan(cmd("Distance", "A", "f"))

    def test_unknown_object(self) -> None:
        with pytest.raises(PlanningError, match="Z"):
            plan(cmd("Distance", "A", "Z"))


class TestRenameAndMove:
    def test_rename(self) -> None:
        result = plan(RenameObject(name="C", new_name="E"), cmd("Distance", "A", "E"))
        assert commands(result) == ['Rename(C, "E")', "m1 = Distance(A, E)"]
        assert result.messages[0] == "C renommé en E."

    def test_rename_to_a_taken_name(self) -> None:
        with pytest.raises(PlanningError, match="déjà utilisé"):
            plan(RenameObject(name="C", new_name="B"))

    def test_move_free_point(self) -> None:
        result = plan(MovePoint(name="C", x=1.5, y=-2))
        assert commands(result) == ["SetCoords(C, 1.5, -2)"]
        assert result.message == "Point C déplacé en (1,5 ; -2)."

    def test_dependent_point_cannot_move(self) -> None:
        with pytest.raises(PlanningError, match="dépend"):
            plan(MovePoint(name="I", x=1, y=1))

    def test_constructed_point_cannot_move_in_the_same_request(self) -> None:
        with pytest.raises(PlanningError):
            plan(cmd("Midpoint", "A", "C", name="M"), MovePoint(name="M", x=1, y=1))


class TestRealGeoGebraState:
    """Shapes of state seen in a real browser (GeoGebra Apps API, 2026-11)."""

    STATE = ConstructionState(
        objects=[
            _point("A", 0, 0, definition="(0, 0)"),
            _point("B", 4, 0, definition="(4, 0)"),
            _point("C", 0, 3, definition="(0, 3)"),
            _point("I", 2, 0, definition="Midpoint[A, B]"),
            GeoObject(name="t1", type="triangle", definition="Polygon[A, B, C]"),
            GeoObject(name="c", type="segment", definition="Segment[A, B, t1]"),
            GeoObject(name="h", type="line", definition="Line[A, C]"),
        ]
    )

    def test_definitions_use_round_brackets(self) -> None:
        assert self.STATE.objects[3].definition == "Midpoint(A, B)"

    def test_free_point_definition_is_its_coordinates(self) -> None:
        plan_actions([MovePoint(name="A", x=1, y=1)], self.STATE, "fr")
        with pytest.raises(PlanningError, match="dépend"):
            plan_actions([MovePoint(name="I", x=1, y=1)], self.STATE, "fr")

    def test_displays_from_bracket_definitions(self) -> None:
        result = plan_actions(
            [cmd("PerpendicularLine", "B", "h"), cmd("Reflect", "B", "c")], self.STATE, "fr"
        )
        assert "à (AC)" in result.messages[0]
        assert "par rapport à la droite [AB]" in result.messages[1]

    def test_image_of_a_polygon_reserves_its_vertices(self) -> None:
        with pytest.raises(PlanningError, match="nom A' est déjà utilisé"):
            plan_actions(
                [cmd("Reflect", "t1", "I"), CreatePoint(name="A'", x=5, y=5)], self.STATE, "fr"
            )

    def test_scripting_commands_are_marked(self) -> None:
        result = plan_actions(
            [RenameObject(name="A", new_name="E"), MovePoint(name="B", x=1, y=1)], self.STATE, "fr"
        )
        assert all(isinstance(s, EvalStep) and s.script for s in result.steps)
