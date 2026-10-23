import pytest

from accessible_geometry.errors import PlanningError
from accessible_geometry.geometry.actions import (
    AskClarification,
    CreateCircle,
    CreateLine,
    CreatePoint,
    CreateRay,
    CreateSegment,
    DeleteObject,
    Redo,
    Undo,
)
from accessible_geometry.geometry.planner import EvalStep, RedoStep, UndoStep, plan_actions
from accessible_geometry.geometry.state import ConstructionState, GeoObject

EMPTY = ConstructionState()


def commands(plan_steps: list[object]) -> list[str]:
    return [step.command for step in plan_steps if isinstance(step, EvalStep)]


class TestPoints:
    def test_point_with_coordinates(self) -> None:
        plan = plan_actions([CreatePoint(name="A", x=1.5, y=-2)], EMPTY, "fr")
        assert commands(plan.steps) == ["A = (1.5, -2)"]
        assert plan.message == "Point A placé en (1,5 ; -2)."

    def test_english_message_uses_decimal_point(self) -> None:
        plan = plan_actions([CreatePoint(name="A", x=1.5, y=-2)], EMPTY, "en")
        assert plan.message == "Point A placed at (1.5, -2)."

    def test_unnamed_points_get_next_free_letters(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([CreatePoint(), CreatePoint()], triangle_points, "en")
        assert [c.split(" =")[0] for c in commands(plan.steps)] == ["D", "E"]

    def test_unpositioned_points_avoid_existing_points(self) -> None:
        plan = plan_actions([CreatePoint(name="A"), CreatePoint(name="B")], EMPTY, "en")
        assert commands(plan.steps) == ["A = (0, 0)", "B = (-2, 0)"]

    def test_name_already_used(self, triangle_points: ConstructionState) -> None:
        with pytest.raises(PlanningError, match="already used"):
            plan_actions([CreatePoint(name="A", x=1, y=1)], triangle_points, "en")

    def test_same_name_twice_in_one_request(self) -> None:
        with pytest.raises(PlanningError):
            plan_actions([CreatePoint(name="A"), CreatePoint(name="A")], EMPTY, "en")


class TestLinesAndCircles:
    def test_segment(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([CreateSegment(start="B", end="C")], triangle_points, "fr")
        assert commands(plan.steps) == ["Segment(B, C)"]
        assert plan.message == "Segment [BC] tracé."

    def test_named_line(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([CreateLine(point1="A", point2="C", name="d")], triangle_points, "fr")
        assert commands(plan.steps) == ["d = Line(A, C)"]
        assert plan.message == "Droite (AC) tracée."

    def test_ray(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([CreateRay(origin="A", through="B")], triangle_points, "fr")
        assert commands(plan.steps) == ["Ray(A, B)"]
        assert plan.message == "Demi-droite [AB) tracée."

    def test_circle_with_radius(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([CreateCircle(center="A", radius=2.5)], triangle_points, "fr")
        assert commands(plan.steps) == ["Circle(A, 2.5)"]
        assert plan.message == "Cercle de centre A et de rayon 2,5 tracé."

    def test_circle_through_point(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions(
            [CreateCircle(center="A", through="B", name="c")], triangle_points, "en"
        )
        assert commands(plan.steps) == ["c = Circle(A, B)"]

    def test_unknown_point(self, triangle_points: ConstructionState) -> None:
        with pytest.raises(PlanningError, match="Z"):
            plan_actions([CreateSegment(start="A", end="Z")], triangle_points, "en")

    def test_reference_to_non_point(self, triangle_points: ConstructionState) -> None:
        with pytest.raises(PlanningError, match="not a point"):
            plan_actions([CreateSegment(start="A", end="f")], triangle_points, "en")

    def test_can_use_points_created_in_same_request(self) -> None:
        plan = plan_actions(
            [
                CreatePoint(name="A", x=0, y=0),
                CreatePoint(name="B", x=3, y=0),
                CreateSegment(start="A", end="B"),
            ],
            EMPTY,
            "en",
        )
        assert commands(plan.steps) == ["A = (0, 0)", "B = (3, 0)", "Segment(A, B)"]
        assert plan.message.count(".") == 3

    def test_failure_rejects_whole_request(self) -> None:
        with pytest.raises(PlanningError):
            plan_actions([CreatePoint(name="A"), CreateSegment(start="A", end="B")], EMPTY, "en")


class TestOtherActions:
    def test_delete(self, triangle_points: ConstructionState) -> None:
        plan = plan_actions([DeleteObject(name="f")], triangle_points, "en")
        assert commands(plan.steps) == ["Delete(f)"]

    def test_deleted_point_cannot_be_used_afterwards(
        self, triangle_points: ConstructionState
    ) -> None:
        with pytest.raises(PlanningError):
            plan_actions(
                [DeleteObject(name="C"), CreateSegment(start="A", end="C")], triangle_points, "en"
            )

    def test_delete_unknown(self) -> None:
        with pytest.raises(PlanningError):
            plan_actions([DeleteObject(name="A")], EMPTY, "en")

    def test_undo_and_redo(self) -> None:
        plan = plan_actions([Undo(steps=2)], EMPTY, "fr")
        assert plan.steps == [UndoStep(), UndoStep()]
        assert plan.message == "2 actions annulées."
        assert plan_actions([Redo()], EMPTY, "en").steps == [RedoStep()]

    def test_clarification_overrides_other_actions(self) -> None:
        plan = plan_actions(
            [CreatePoint(name="A"), AskClarification(question="Quel point ?")], EMPTY, "fr"
        )
        assert plan.status == "clarification"
        assert plan.steps == []
        assert plan.message == "Quel point ?"


def test_state_points_without_coordinates_do_not_block_placement() -> None:
    state = ConstructionState(objects=[GeoObject(name="A", type="point")])
    plan = plan_actions([CreatePoint()], state, "en")
    assert commands(plan.steps) == ["B = (0, 0)"]
