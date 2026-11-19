"""Offline checks of the phrase test set and its runner (the run itself needs Groq)."""

import pytest

from accessible_geometry.geometry.planner import EvalStep, UndoStep
from accessible_geometry.service import CommandResult
from tests.eval.run_eval import Case, Figure, check, load_cases, split_names


def _result(*commands: str, status: str = "executed") -> CommandResult:
    return CommandResult.model_validate(
        {
            "status": status,
            "transcript": "",
            "message": "",
            "steps": [EvalStep(command=c).model_dump() for c in commands],
        }
    )


def _case(expect: dict[str, object], figure: dict[str, object] | None = None) -> Case:
    return Case.model_validate(
        {"id": "t", "language": "fr", "text": "t", "figure": figure or {}, "expect": expect}
    )


def _check(case: Case, result: CommandResult) -> list[str]:
    return check(case, Figure.from_spec(case.figure), result)


def test_phrase_file_is_valid() -> None:
    cases = load_cases()
    assert len(cases) >= 20
    assert {case.language for case in cases} == {"fr", "en"}
    for case in cases:  # every figure can be sent to the interpreter
        Figure.from_spec(case.figure).to_state()


def test_split_names() -> None:
    assert split_names("AB") == ["A", "B"]
    assert split_names("AC1B'") == ["A", "C1", "B'"]
    with pytest.raises(ValueError):
        split_names("Ab")


SQUARE = {
    "new_points": 4,
    "segments": ["AB", "BC", "CD", "DA"],
    "distances": {"AB": 4, "BC": 4, "CD": 4, "DA": 4},
    "right_angles": ["ABC", "BCD"],
}
SQUARE_POINTS = ("A = (0, 0)", "B = (4, 0)", "C = (4, 4)", "D = (0, 4)")
SQUARE_SIDES = ("Segment(A, B)", "Segment(B, C)", "Segment(C, D)", "Segment(D, A)")


def test_square_passes() -> None:
    assert _check(_case(SQUARE), _result(*SQUARE_POINTS, *SQUARE_SIDES)) == []


def test_wrong_square_fails() -> None:
    points = ("A = (0, 0)", "B = (4, 0)", "C = (5, 3)", "D = (0, 4)")
    failures = _check(_case(SQUARE), _result(*points, *SQUARE_SIDES[:3]))
    assert "segment DA is missing" in failures
    assert "angle ABC is not right" in failures
    assert any(f.startswith("BC = ") for f in failures)


def test_status_and_missing_point() -> None:
    clarification = _result(status="clarification")
    assert _check(_case({}), clarification) == ["status clarification, expected executed"]
    assert _check(_case({"status": ["clarification", "rejected"]}), clarification) == []
    assert _check(_case({"distances": {"AB": 1}}), _result()) == ["point A is missing"]


def test_delete_removes_dependents_and_undo_counts() -> None:
    figure = {"points": {"A": [0, 0], "B": [4, 0]}, "segments": ["AB"]}
    case = _case({"absent": ["A"], "new_segments": 0}, figure)
    assert _check(case, _result("Delete(A)")) == []
    undo = CommandResult(status="executed", transcript="", message="", steps=[UndoStep()] * 2)
    assert _check(_case({"undo": 2}), undo) == []


def test_circles_and_view() -> None:
    case = _case({"circles": [{"center": "O", "radius": 2}]})
    assert _check(case, _result("O = (4, 0)", "Circle(O, 2)")) == []
    assert _check(case, _result("O = (4, 0)", "Circle(O, 3)")) != []
    assert _check(_case({}), _result("A = (40, 0)")) == ["A at (40, 0) is out of view"]
