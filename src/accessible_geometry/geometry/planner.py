"""Turn validated geometry actions into GeoGebra steps for the browser to execute.

Planning is all-or-nothing: if any action of a request cannot be applied (unknown
point, name already taken...), a `PlanningError` is raised and the figure stays
unchanged. Feedback messages are built here, deterministically, from the action
parameters, rather than written by the LLM.
"""

import math
import string
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from accessible_geometry.errors import PlanningError
from accessible_geometry.geometry.actions import (
    AskClarification,
    CreateCircle,
    CreateLine,
    CreatePoint,
    CreateRay,
    CreateSegment,
    DeleteObject,
    GeometryAction,
    Redo,
    Undo,
)
from accessible_geometry.geometry.state import ConstructionState
from accessible_geometry.i18n import Language, format_number, translate

# Where unpositioned points go: a grid around the origin, nearest positions first.
_GRID_SPACING = 2
_GRID_HALF_SIZE = 5
_MIN_POINT_DISTANCE = 1.5
_FREE_POSITIONS = sorted(
    (
        (float(i * _GRID_SPACING), float(j * _GRID_SPACING))
        for i in range(-_GRID_HALF_SIZE, _GRID_HALF_SIZE + 1)
        for j in range(-_GRID_HALF_SIZE, _GRID_HALF_SIZE + 1)
    ),
    key=lambda p: (math.hypot(*p), p),
)


class EvalStep(BaseModel):
    """Run one GeoGebra command with `ggbApplet.evalCommand`."""

    op: Literal["eval"] = "eval"
    command: str


class UndoStep(BaseModel):
    op: Literal["undo"] = "undo"


class RedoStep(BaseModel):
    op: Literal["redo"] = "redo"


Step = Annotated[EvalStep | UndoStep | RedoStep, Field(discriminator="op")]
PlanStatus = Literal["executed", "clarification"]


@dataclass
class Plan:
    status: PlanStatus
    steps: list[Step] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        return " ".join(self.messages)


def plan_actions(
    actions: list[GeometryAction], state: ConstructionState, language: Language
) -> Plan:
    """Validate `actions` against `state` and translate them into steps."""
    return _Planner(state, language).plan(actions)


class _Planner:
    def __init__(self, state: ConstructionState, language: Language) -> None:
        self._language = language
        self._names = {obj.name for obj in state.objects}
        self._point_names = {obj.name for obj in state.objects if obj.is_point}
        self._point_positions = [
            (obj.x, obj.y) for obj in state.objects if obj.x is not None and obj.y is not None
        ]

    def plan(self, actions: list[GeometryAction]) -> Plan:
        # A clarification question replaces everything else: never act on a guess.
        for action in actions:
            if isinstance(action, AskClarification):
                return Plan(status="clarification", messages=[action.question])

        plan = Plan(status="executed")
        for action in actions:
            self._add(plan, action)
        return plan

    def _add(self, plan: Plan, action: GeometryAction) -> None:
        match action:
            case CreatePoint():
                self._create_point(plan, action)
            case CreateSegment(start=a, end=b):
                self._require_points(a, b)
                plan.steps.append(EvalStep(command=f"Segment({a}, {b})"))
                plan.messages.append(self._t("segment_created", a=a, b=b))
            case CreateLine(point1=a, point2=b, name=name):
                self._require_points(a, b)
                plan.steps.append(EvalStep(command=self._labeled(name, f"Line({a}, {b})")))
                plan.messages.append(self._t("line_created", a=a, b=b))
            case CreateRay(origin=a, through=b, name=name):
                self._require_points(a, b)
                plan.steps.append(EvalStep(command=self._labeled(name, f"Ray({a}, {b})")))
                plan.messages.append(self._t("ray_created", a=a, b=b))
            case CreateCircle():
                self._create_circle(plan, action)
            case DeleteObject(name=name):
                self._require_existing(name)
                self._names.discard(name)
                self._point_names.discard(name)
                plan.steps.append(EvalStep(command=f"Delete({name})"))
                plan.messages.append(self._t("object_deleted", name=name))
            case Undo(steps=count):
                plan.steps.extend(UndoStep() for _ in range(count))
                plan.messages.append(
                    self._t("undone") if count == 1 else self._t("undone_many", count=count)
                )
            case Redo(steps=count):
                plan.steps.extend(RedoStep() for _ in range(count))
                plan.messages.append(
                    self._t("redone") if count == 1 else self._t("redone_many", count=count)
                )
            case _:
                raise TypeError(f"unsupported action {type(action).__name__}")

    def _create_point(self, plan: Plan, action: CreatePoint) -> None:
        name = action.name or self._next_free_point_name()
        self._claim_name(name)
        if action.x is not None and action.y is not None:
            x, y = action.x, action.y
        else:
            x, y = self._free_position()
        self._point_names.add(name)
        self._point_positions.append((x, y))
        plan.steps.append(EvalStep(command=f"{name} = ({_num(x)}, {_num(y)})"))
        plan.messages.append(
            self._t(
                "point_created",
                name=name,
                x=format_number(x, self._language),
                y=format_number(y, self._language),
            )
        )

    def _create_circle(self, plan: Plan, action: CreateCircle) -> None:
        self._require_points(action.center)
        if action.through is not None:
            self._require_points(action.through)
            command = f"Circle({action.center}, {action.through})"
            message = self._t(
                "circle_through_created", center=action.center, through=action.through
            )
        else:
            assert action.radius is not None  # guaranteed by CreateCircle validation
            command = f"Circle({action.center}, {_num(action.radius)})"
            message = self._t(
                "circle_radius_created",
                center=action.center,
                radius=format_number(action.radius, self._language),
            )
        plan.steps.append(EvalStep(command=self._labeled(action.name, command)))
        plan.messages.append(message)

    def _labeled(self, name: str | None, command: str) -> str:
        if name is None:
            return command
        self._claim_name(name)
        return f"{name} = {command}"

    def _claim_name(self, name: str) -> None:
        if name in self._names:
            raise PlanningError(self._t("name_taken", name=name))
        self._names.add(name)

    def _require_existing(self, name: str) -> None:
        if name not in self._names:
            raise PlanningError(self._t("unknown_object", name=name))

    def _require_points(self, *names: str) -> None:
        for name in names:
            self._require_existing(name)
            if name not in self._point_names:
                raise PlanningError(self._t("not_a_point", name=name))

    def _next_free_point_name(self) -> str:
        suffixes = ("", *(f"_{i}" for i in range(1, 100)))
        for suffix in suffixes:
            for letter in string.ascii_uppercase:
                if (candidate := letter + suffix) not in self._names:
                    return candidate
        raise PlanningError(self._t("not_understood"))  # 2,600 points: not a real case

    def _free_position(self) -> tuple[float, float]:
        for candidate in _FREE_POSITIONS:
            if all(
                math.dist(candidate, existing) >= _MIN_POINT_DISTANCE
                for existing in self._point_positions
            ):
                return candidate
        return _FREE_POSITIONS[0]

    def _t(self, key: str, **params: object) -> str:
        return translate(key, self._language, **params)


def _num(value: float) -> str:
    """Format a number for a GeoGebra command: decimal point, up to 4 decimals."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
