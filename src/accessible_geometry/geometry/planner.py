"""Turn validated geometry actions into GeoGebra steps for the browser to execute.

Planning is all-or-nothing: if any action of a request cannot be applied (unknown
point, name already taken...), a `PlanningError` is raised and the figure stays
unchanged. Feedback messages are built here, deterministically, from the action
parameters, rather than written by the LLM. A measured value is only known once
GeoGebra has computed it: its message holds a `{{name}}` placeholder that the
browser replaces with the value of the object `name`.
"""

import math
import re
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
    GeoGebraCommand,
    GeometryAction,
    MovePoint,
    Redo,
    RenameObject,
    Undo,
)
from accessible_geometry.geometry.commands import COMMANDS, FIGURE_KINDS, Kind, Overload, kind_of
from accessible_geometry.geometry.state import ConstructionState, GeoObject
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

# Default names of created objects, by kind: d, d1, d2... for lines.
_NAME_PREFIXES: dict[Kind, str] = {"line": "d", "circle": "c", "polygon": "p", "number": "m"}
# How the student writes an object defined from two points: [AB], (AB), [AB).
_TWO_POINT_NOTATION = {"Segment": "[{}{}]", "Line": "({}{})", "Ray": "[{}{})"}
_DEFINITION = re.compile(r"(\w+)\(([^()]*)\)")
# A free point's definition is its coordinates, e.g. "(1, 2)".
_COMMAND_CALL = re.compile(r"[A-Za-z]\w*\(")


class EvalStep(BaseModel):
    """Run one GeoGebra command with `ggbApplet.evalCommand`.

    `label` is the name the command creates: the browser refuses to run it if an
    object of that name already exists, since GeoGebra would silently redefine it.
    `script` marks scripting commands (Rename, SetCoords): GeoGebra reports them as
    failed even when they work, so the browser ignores their result.
    """

    op: Literal["eval"] = "eval"
    command: str
    label: str | None = None
    script: bool = False


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


@dataclass
class _Object:
    kind: Kind | None  # None: an object the actions cannot use (text, vector...)
    display: str  # how messages refer to it: A, [AB], (AB), ABC...
    free: bool = False  # a point that can be moved
    vertices: tuple[str, ...] = ()  # of a polygon


class _Planner:
    def __init__(self, state: ConstructionState, language: Language) -> None:
        self._language = language
        self._objects = {obj.name: _from_state(obj) for obj in state.objects}
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
                self._two_point_object(plan, "Segment", a, b, None, "segment_created")
            case CreateLine(point1=a, point2=b, name=name):
                self._two_point_object(plan, "Line", a, b, name, "line_created")
            case CreateRay(origin=a, through=b, name=name):
                self._two_point_object(plan, "Ray", a, b, name, "ray_created")
            case CreateCircle():
                self._create_circle(plan, action)
            case GeoGebraCommand():
                self._geogebra_command(plan, action)
            case RenameObject(name=old, new_name=new):
                obj = self._require_existing(old)
                self._claim(new, obj.kind, new if obj.display == old else obj.display, obj.free)
                del self._objects[old]
                plan.steps.append(EvalStep(command=f'Rename({old}, "{new}")', script=True))
                plan.messages.append(self._t("renamed", name=old, new_name=new))
            case MovePoint(name=name, x=x, y=y):
                if not self._require_points(name)[0].free:
                    raise PlanningError(self._t("point_not_free", name=name))
                self._point_positions.append((x, y))
                plan.steps.append(
                    EvalStep(command=f"SetCoords({name}, {_num(x)}, {_num(y)})", script=True)
                )
                plan.messages.append(self._t("point_moved", name=name, **self._xy(x, y)))
            case DeleteObject(name=name):
                self._require_existing(name)
                del self._objects[name]
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
        name = action.name or self._free_point_name()
        self._claim(name, "point", name, free=True)
        if action.x is not None and action.y is not None:
            x, y = action.x, action.y
        else:
            x, y = self._free_position()
        self._point_positions.append((x, y))
        plan.steps.append(EvalStep(command=f"{name} = ({_num(x)}, {_num(y)})", label=name))
        plan.messages.append(self._t("point_created", name=name, **self._xy(x, y)))

    def _two_point_object(
        self, plan: Plan, command: str, a: str, b: str, name: str | None, message: str
    ) -> None:
        self._require_points(a, b)
        if name is not None:
            self._claim(name, "line", _TWO_POINT_NOTATION[command].format(a, b))
        plan.steps.append(EvalStep(command=_labeled(name, f"{command}({a}, {b})"), label=name))
        plan.messages.append(self._t(message, a=a, b=b))

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
        if action.name is not None:
            self._claim(action.name, "circle", action.name)
        plan.steps.append(EvalStep(command=_labeled(action.name, command), label=action.name))
        plan.messages.append(message)

    def _geogebra_command(self, plan: Plan, action: GeoGebraCommand) -> None:
        names = [arg for arg in action.args if isinstance(arg, str)]
        for name in names:
            self._require_existing(name)
        overload = self._overload(action)

        result: Kind | None
        if overload.result == "same":
            first = action.args[0]
            assert isinstance(first, str)  # a "figure" parameter
            result = self._objects[first].kind
        else:
            result = overload.result
        name = action.name or self._default_name(result, action)

        displays = [
            self._objects[arg].display if isinstance(arg, str) else self._number(arg)
            for arg in action.args
        ]
        points_only = all(self._objects[n].kind == "point" for n in names)
        params: dict[str, object] = {f"a{i}": d for i, d in enumerate(displays)}
        params["all"] = ("" if points_only and len(names) > 1 else ", ").join(displays)
        params["value"] = "{{" + name + "}}"

        display = _command_display(result, name, displays if overload.variadic else [])
        self._claim(name, result, display)
        params["name"] = display
        if action.command == "Polygon":
            self._objects[name].vertices = tuple(names)
            self._reserve_polygon_parts(names, "")
        elif overload.result == "same" and self._objects[names[0]].kind == "polygon":
            # The image of polygon ABC comes with its own vertices A', B', C'.
            source = self._objects[names[0]].vertices
            self._objects[name].vertices = tuple(v + "'" for v in source)
            self._reserve_polygon_parts(source, "'")

        args = [arg if isinstance(arg, str) else _num(arg) for arg in action.args]
        command = overload.template.format(*args, all=", ".join(args))
        plan.steps.append(EvalStep(command=f"{name} = {command}", label=name))
        plan.messages.append(self._t(overload.message, **params))

    def _reserve_polygon_parts(self, vertices: list[str] | tuple[str, ...], suffix: str) -> None:
        """Names GeoGebra gives to the parts of a polygon, so that nothing else takes them.

        Polygon(A, B, C) also creates its sides a, b, c (named after the opposite
        vertex); its image creates A', B', C' and a', b', c'.
        """
        for vertex in vertices:
            if suffix:
                self._objects.setdefault(vertex + suffix, _Object("point", vertex + suffix))
            if re.fullmatch(r"[A-Z]'*", vertex):
                side = vertex.lower() + suffix
                self._objects.setdefault(side, _Object("line", side))

    def _overload(self, action: GeoGebraCommand) -> Overload:
        for overload in COMMANDS[action.command]:
            if overload.accepts_count(len(action.args)) and all(
                self._fits(arg, overload.param(i)) for i, arg in enumerate(action.args)
            ):
                return overload
        shown = ", ".join(a if isinstance(a, str) else self._number(a) for a in action.args)
        raise PlanningError(self._t("wrong_arguments", args=shown))

    def _fits(self, arg: str | float, param: str) -> bool:
        if isinstance(arg, float):
            return param == "number"
        kind = self._objects[arg].kind
        return kind in FIGURE_KINDS if param == "figure" else kind == param

    def _default_name(self, kind: Kind | None, action: GeoGebraCommand) -> str:
        source = action.args[0]
        if action.command in ("Reflect", "Translate", "Rotate") and isinstance(source, str):
            # The image of A is A', then A''.
            for primes in ("'", "''", "'''"):
                if source + primes not in self._objects:
                    return source + primes
        if kind == "point":
            return self._free_point_name()
        prefix = _NAME_PREFIXES.get(kind, "obj") if kind else "obj"
        start = "" if kind == "line" else "1"
        for suffix in (start, *map(str, range(1, 100))):
            if prefix + suffix not in self._objects:
                return prefix + suffix
        raise PlanningError(self._t("not_understood"))  # 100 lines: not a real case

    def _claim(self, name: str, kind: Kind | None, display: str, free: bool = False) -> None:
        if name in self._objects:
            raise PlanningError(self._t("name_taken", name=name))
        self._objects[name] = _Object(kind, display, free)

    def _require_existing(self, name: str) -> _Object:
        if name not in self._objects:
            raise PlanningError(self._t("unknown_object", name=name))
        return self._objects[name]

    def _require_points(self, *names: str) -> list[_Object]:
        objects = [self._require_existing(name) for name in names]
        for name, obj in zip(names, objects, strict=True):
            if obj.kind != "point":
                raise PlanningError(self._t("not_a_point", name=name))
        return objects

    def _free_point_name(self) -> str:
        suffixes = ("", *(f"_{i}" for i in range(1, 100)))
        for suffix in suffixes:
            for letter in string.ascii_uppercase:
                if (candidate := letter + suffix) not in self._objects:
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

    def _number(self, value: float) -> str:
        return format_number(value, self._language)

    def _xy(self, x: float, y: float) -> dict[str, str]:
        return {"x": self._number(x), "y": self._number(y)}

    def _t(self, key: str, **params: object) -> str:
        return translate(key, self._language, **params)


def _from_state(obj: GeoObject) -> _Object:
    kind = kind_of(obj.type)
    display = obj.name
    if obj.definition and (match := _DEFINITION.fullmatch(obj.definition.strip())):
        command, args = match[1], [a.strip() for a in match[2].split(",")]
        vertices: tuple[str, ...] = ()
        # A polygon side is defined as Segment(A, B, p1).
        if command in _TWO_POINT_NOTATION and len(args) in (2, 3):
            display = _TWO_POINT_NOTATION[command].format(*args[:2])
        elif command == "Polygon" and all(re.fullmatch(r"[A-Z]\w*'*", a) for a in args):
            display, vertices = "".join(args), tuple(args)
        return _Object(kind, display, vertices=vertices)
    free = kind == "point" and not (obj.definition and _COMMAND_CALL.match(obj.definition))
    return _Object(kind, display, free=free)


def _command_display(kind: Kind | None, name: str, vertices: list[str]) -> str:
    if kind == "polygon" and vertices:
        return "".join(vertices)
    return f"({name})" if kind == "line" else name


def _labeled(name: str | None, command: str) -> str:
    return command if name is None else f"{name} = {command}"


def _num(value: float) -> str:
    """Format a number for a GeoGebra command: decimal point, up to 4 decimals."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
