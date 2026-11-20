"""Run the phrase test set (`phrases.yaml`) against the real LLM and print a score.

    uv run python -m tests.eval.run_eval                  # every case
    uv run python -m tests.eval.run_eval square midpoint  # cases whose id contains a word
    uv run python -m tests.eval.run_eval -v               # also log the app's INFO lines

Each phrase goes through the real pipeline (Groq interpreter + planner); the planned
GeoGebra steps are then replayed on a simple model of the figure and checked against
the expected outcome. Needs GROQ_API_KEY (read from `.env` like the app does), so it is
kept out of pytest and CI; `tests/test_eval_runner.py` checks this file offline.
"""

import argparse
import asyncio
import logging
import math
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import groq
import yaml
from pydantic import BaseModel, ConfigDict, Field

from accessible_geometry.config import get_settings
from accessible_geometry.conversation import Exchange
from accessible_geometry.geometry.planner import EvalStep, RedoStep, UndoStep
from accessible_geometry.geometry.state import ConstructionState, GeoObject
from accessible_geometry.llm.interpreter import GroqInterpreter
from accessible_geometry.service import CommandResult, CommandStatus, VoiceCommandService
from tests.fakes import FakeTranscriber

PHRASES_FILE = Path(__file__).with_name("phrases.yaml")
TOLERANCE = 1e-3
VIEW_X = 10.0
VIEW_Y = 8.0

Point = tuple[float, float]
_NAME = r"[A-Za-z][A-Za-z0-9_']*"
_NUM = r"-?\d+(?:\.\d+)?"


# --- Test set format -------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CircleSpec(_Strict):
    name: str | None = None
    center: str | None = None
    radius: float | None = None
    through: str | None = None


class FigureSpec(_Strict):
    points: dict[str, tuple[float, float]] = {}
    segments: list[str] = []
    lines: list[str] = []
    circles: list[CircleSpec] = []


class Expect(_Strict):
    status: CommandStatus | list[CommandStatus] = "executed"
    new_points: int | None = None
    new_segments: int | None = None
    points: list[str] | dict[str, tuple[float, float]] = []
    absent: list[str] = []
    segments: list[str] = []
    lines: list[str] = []
    rays: list[str] = []
    circles: list[CircleSpec] = []
    distances: dict[str, float] = {}
    equal: list[tuple[str, str]] = []
    right_angles: list[str] = []
    not_collinear: list[str] = []
    undo: int | None = None
    redo: int | None = None
    commands: list[str] = []  # regular expressions, each matching a GeoGebra command
    in_view: bool = True


class Case(_Strict):
    id: str
    language: Literal["fr", "en"]
    text: str
    figure: FigureSpec = FigureSpec()
    history: list[Exchange] = Field(default_factory=list)
    expect: Expect = Expect()


def load_cases(path: Path = PHRASES_FILE) -> list[Case]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = [Case.model_validate(item) for item in data]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in the phrase test set")
    return cases


def split_names(text: str) -> list[str]:
    """'AB' -> ['A', 'B']; "AC1" -> ['A', 'C1']; "A'B" -> ["A'", 'B']."""
    names = re.findall(r"[A-Z][0-9]*'*", text)
    if "".join(names) != text:
        raise ValueError(f"cannot split {text!r} into point names")
    return names


# --- Figure model ----------------------------------------------------------------------


@dataclass
class Shape:
    kind: str  # segment, line, ray, circle, polygon, number, or point without coordinates
    refs: tuple[str, ...]  # point names the shape is defined from
    radius: float | None = None


@dataclass
class Figure:
    """Just enough of a GeoGebra construction to check the planned steps."""

    points: dict[str, Point] = field(default_factory=dict)
    shapes: dict[str, Shape] = field(default_factory=dict)
    created: dict[str, int] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    undo: int = 0
    redo: int = 0
    _auto: int = 0

    @classmethod
    def from_spec(cls, spec: FigureSpec) -> "Figure":
        figure = cls(points=dict(spec.points))
        for kind, pairs in (("segment", spec.segments), ("line", spec.lines)):
            for pair in pairs:
                figure.shapes[figure._auto_name()] = Shape(kind, tuple(split_names(pair)))  # type: ignore[arg-type]
        for circle in spec.circles:
            assert circle.center is not None
            refs = (circle.center,) if circle.through is None else (circle.center, circle.through)
            figure.shapes[circle.name or figure._auto_name()] = Shape("circle", refs, circle.radius)
        return figure

    def to_state(self) -> ConstructionState:
        objects = [
            GeoObject(name=name, type="point", value=f"({x:g}, {y:g})", x=x, y=y)
            for name, (x, y) in self.points.items()
        ]
        for name, shape in self.shapes.items():
            args = ", ".join(
                [*shape.refs, *([] if shape.radius is None else [f"{shape.radius:g}"])]
            )
            objects.append(
                GeoObject(name=name, type=shape.kind, definition=f"{shape.kind.title()}({args})")
            )
        return ConstructionState(objects=objects)

    def names(self) -> set[str]:
        return set(self.points) | set(self.shapes)

    def apply(self, steps: list[Any]) -> None:
        for step in steps:
            if isinstance(step, UndoStep):
                self.undo += 1
            elif isinstance(step, RedoStep):
                self.redo += 1
            elif isinstance(step, EvalStep):
                self._eval(step.command)

    def _eval(self, command: str) -> None:
        self.commands.append(command)
        if m := re.fullmatch(rf"({_NAME}) = \(({_NUM}), ({_NUM})\)", command):
            self.points[m[1]] = (float(m[2]), float(m[3]))
            self._count("point")
        elif m := re.fullmatch(rf"SetCoords\(({_NAME}), ({_NUM}), ({_NUM})\)", command):
            self.point(m[1])
            self.points[m[1]] = (float(m[2]), float(m[3]))
        elif m := re.fullmatch(rf'Rename\(({_NAME}), "({_NAME})"\)', command):
            if m[1] in self.points:
                self.points[m[2]] = self.points.pop(m[1])
            else:
                self.shapes[m[2]] = self.shapes.pop(m[1])
        elif m := re.fullmatch(
            rf"({_NAME}) = (Midpoint|Intersect|Reflect|Translate|Rotate|Polygon"
            rf"|PerpendicularLine|PerpendicularBisector|AngleBisector|Distance|Area"
            rf"|Perimeter|If)\((.*)\)",
            command,
        ):
            self._construct(m[1], m[2], m[3])
        else:
            self._two_point_object(command)

    def _construct(self, label: str, command: str, inside: str) -> None:
        """A whitelisted command: record what it creates, with coordinates when easy."""
        refs = tuple(dict.fromkeys(n for n in re.findall(_NAME, inside) if n in self.names()))
        args = [a.strip() for a in inside.split(",")]
        kinds = {"Polygon": "polygon", "Midpoint": "point", "Intersect": "point"}
        if command in ("Reflect", "Translate", "Rotate"):
            first = args[0]
            kind = "point" if first in self.points else self.shapes[first].kind
        elif command in kinds:
            kind = kinds[command]
        elif command.endswith(("Line", "Bisector")):
            kind = "line"
        else:
            kind = "number"

        position = self._position(command, args) if kind == "point" else None
        if position is not None:
            self.points[label] = position
        else:
            self.shapes[label] = Shape(kind, refs)
        self._count(kind)
        if command == "Polygon":
            for a, b in zip(args, [*args[1:], args[0]], strict=True):
                self.shapes[self._auto_name()] = Shape("segment", (a, b))

    def _position(self, command: str, args: list[str]) -> Point | None:
        names = [n for n in re.findall(_NAME, ", ".join(args)) if n != "Vector"]
        if not all(n in self.points for n in names):
            return None  # built from a line or circle: not computed here
        p = [self.points[n] for n in names]
        if command == "Midpoint":
            return ((p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2)
        if command == "Reflect":
            return (2 * p[1][0] - p[0][0], 2 * p[1][1] - p[0][1])
        if command == "Translate":
            return (p[0][0] + p[2][0] - p[1][0], p[0][1] + p[2][1] - p[1][1])
        if command == "Rotate":
            angle = math.radians(float(args[1].rstrip("°")))
            (px, py), (cx, cy) = p
            dx, dy = px - cx, py - cy
            return (
                cx + dx * math.cos(angle) - dy * math.sin(angle),
                cy + dx * math.sin(angle) + dy * math.cos(angle),
            )
        return None

    def _two_point_object(self, command: str) -> None:
        name, num = _NAME, _NUM
        if m := re.fullmatch(
            rf"(?:({name}) = )?(Segment|Line|Ray|Circle)\(({name}), ({name}|{num})\)", command
        ):
            kind = m[2].lower()
            second = m[4]
            is_radius = re.fullmatch(num, second) is not None
            refs = (m[3],) if is_radius else (m[3], second)
            radius = float(second) if is_radius else None
            self.shapes[m[1] or self._auto_name()] = Shape(kind, refs, radius)  # type: ignore[arg-type]
            self._count(kind)
        elif m := re.fullmatch(rf"Delete\(({name})\)", command):
            self._delete(m[1])
        else:
            raise ValueError(f"the eval runner does not know the command {command!r}")

    def _delete(self, target: str) -> None:
        self.points.pop(target, None)
        self.shapes.pop(target, None)
        for name, shape in list(self.shapes.items()):
            if target in shape.refs:
                self._delete(name)

    def _count(self, kind: str) -> None:
        self.created[kind] = self.created.get(kind, 0) + 1

    def _auto_name(self) -> str:
        """Name an unnamed object like GeoGebra does: f, g, h... then f_1, g_1..."""
        while True:
            letter, round_ = "fghijklmnpqrstuvwz"[self._auto % 18], self._auto // 18
            self._auto += 1
            name = letter if round_ == 0 else f"{letter}_{round_}"
            if name not in self.names():
                return name

    # Queries used by the checks.

    def has(self, kind: str, pair: str) -> bool:
        a, b = split_names(pair)
        wanted = {(a, b)} if kind == "ray" else {(a, b), (b, a)}
        return any(s.kind == kind and s.refs in wanted for s in self.shapes.values())

    def circle_radius(self, shape: Shape) -> float | None:
        if shape.radius is not None:
            return shape.radius
        center, through = (self.points.get(n) for n in shape.refs)
        return math.dist(center, through) if center and through else None

    def distance(self, pair: str) -> float:
        a, b = (self.point(n) for n in split_names(pair))
        return math.dist(a, b)

    def has_point(self, name: str) -> bool:
        return name in self.points or getattr(self.shapes.get(name), "kind", None) == "point"

    def point(self, name: str) -> Point:
        if name in self.shapes and self.shapes[name].kind == "point":
            raise KeyError(f"point {name} is constructed: its position is not computed here")
        if name not in self.points:
            raise KeyError(f"point {name} is missing")
        return self.points[name]


# --- Checks ----------------------------------------------------------------------------


def check(case: Case, before: Figure, result: CommandResult) -> list[str]:
    """Return the reasons why `result` does not match `case.expect` (empty: pass)."""
    expect = case.expect
    accepted = [expect.status] if isinstance(expect.status, str) else expect.status
    if result.status not in accepted:
        return [f"status {result.status}, expected {' or '.join(accepted)}"]
    if result.status != "executed":
        return []

    after = Figure(points=dict(before.points), shapes=dict(before.shapes), _auto=before._auto)
    try:
        after.apply(result.steps)
        return _check_figure(expect, before, after)
    except (KeyError, ValueError) as exc:
        return [str(exc).strip("'\"")]


def _check_figure(expect: Expect, before: Figure, after: Figure) -> list[str]:
    failures: list[str] = []

    def close(value: float, target: float) -> bool:
        return abs(value - target) <= TOLERANCE * max(1.0, abs(target))

    for kind, wanted in (("point", expect.new_points), ("segment", expect.new_segments)):
        got = after.created.get(kind, 0)
        if wanted is not None and got != wanted:
            failures.append(f"{got} new {kind}s, expected {wanted}")

    if isinstance(expect.points, dict):
        for name, (x, y) in expect.points.items():
            px, py = after.point(name)
            if not (close(px, x) and close(py, y)):
                failures.append(f"{name} at ({px:g}, {py:g}), expected ({x:g}, {y:g})")
    else:
        failures += [f"point {n} is missing" for n in expect.points if not after.has_point(n)]
    failures += [f"{n} should not exist" for n in expect.absent if n in after.names()]

    for kind, pairs in (("segment", expect.segments), ("line", expect.lines)):
        failures += [f"{kind} {p} is missing" for p in pairs if not after.has(kind, p)]
    failures += [f"ray [{p}) is missing" for p in expect.rays if not after.has("ray", p)]

    for pattern in expect.commands:
        if not any(re.fullmatch(pattern, command) for command in after.commands):
            failures.append(f"no command matching {pattern}")

    for spec in expect.circles:
        if not any(_circle_matches(after, shape, spec) for shape in after.shapes.values()):
            failures.append(f"no circle matching {spec.model_dump(exclude_none=True)}")

    for pair, length in expect.distances.items():
        if not close(got := after.distance(pair), length):
            failures.append(f"{pair} = {got:.4g}, expected {length:g}")
    for first, second in expect.equal:
        if not close(after.distance(first), after.distance(second)):
            failures.append(f"{first} and {second} are not equal")

    for triple in expect.right_angles:
        a, b, c = (after.point(n) for n in split_names(triple))
        u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
        if abs(u[0] * v[0] + u[1] * v[1]) > TOLERANCE * math.hypot(*u) * math.hypot(*v):
            failures.append(f"angle {triple} is not right")
    for triple in expect.not_collinear:
        a, b, c = (after.point(n) for n in split_names(triple))
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1])
        if abs(u[0] * v[1] - u[1] * v[0]) <= 0.05 * math.hypot(*u) * math.hypot(*v):
            failures.append(f"{triple} is (almost) flat")

    for label, wanted, got in (
        ("undo", expect.undo, after.undo),
        ("redo", expect.redo, after.redo),
    ):
        if wanted is not None and got != wanted:
            failures.append(f"{got} {label} steps, expected {wanted}")

    if expect.in_view:
        for name, (x, y) in after.points.items():
            if before.points.get(name) != (x, y) and (abs(x) > VIEW_X or abs(y) > VIEW_Y):
                failures.append(f"{name} at ({x:g}, {y:g}) is out of view")
    return failures


def _circle_matches(figure: Figure, shape: Shape, spec: CircleSpec) -> bool:
    if shape.kind != "circle":
        return False
    if spec.center is not None and shape.refs[0] != spec.center:
        return False
    if spec.through is not None and shape.refs[1:] != (spec.through,):
        return False
    radius = figure.circle_radius(shape)
    return spec.radius is None or (radius is not None and abs(radius - spec.radius) <= TOLERANCE)


# --- Runner ----------------------------------------------------------------------------


async def run(cases: list[Case], model: str) -> int:
    settings = get_settings()
    if not settings.has_api_key:
        print("GROQ_API_KEY is not set (see .env.example).", file=sys.stderr)
        return 2
    assert settings.groq_api_key is not None
    # Free-tier rate limits: let the SDK wait and retry more than usual.
    client = groq.AsyncGroq(
        api_key=settings.groq_api_key.get_secret_value(), timeout=60, max_retries=8
    )
    service = VoiceCommandService(FakeTranscriber(""), GroqInterpreter(client, model))
    print(f"Model {model}, {len(cases)} cases\n")

    passed = 0
    started = time.perf_counter()
    try:
        for case in cases:
            before = Figure.from_spec(case.figure)
            result = await service.handle_text(
                case.text, before.to_state(), case.language, case.history
            )
            failures = check(case, before, result)
            passed += not failures
            print(f"{'PASS' if not failures else 'FAIL'}  {case.id}: {case.text!r}")
            if failures:
                for failure in failures:
                    print(f"        - {failure}")
                print(f"        answer ({result.status}): {result.message}")
                for step in result.steps:
                    print(f"        step: {step.model_dump_json()}")
    finally:
        await client.close()

    elapsed = time.perf_counter() - started
    print(f"\nScore: {passed}/{len(cases)} ({100 * passed / len(cases):.0f}%) in {elapsed:.0f} s")
    return 0 if passed == len(cases) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("filters", nargs="*", help="run only cases whose id contains one")
    parser.add_argument("--model", help="LLM model (default: the app's LLM_MODEL)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show INFO logs")
    args = parser.parse_args()
    # Print each result as it comes, so that a stopped run (rate limits) keeps them.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cases = [
        case
        for case in load_cases()
        if not args.filters or any(word in case.id for word in args.filters)
    ]
    if not cases:
        sys.exit("no case matches")
    sys.exit(asyncio.run(run(cases, args.model or get_settings().llm_model)))


if __name__ == "__main__":
    main()
