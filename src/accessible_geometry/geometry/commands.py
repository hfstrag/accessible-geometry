"""The whitelist of GeoGebra commands the LLM may request through `geogebra_command`.

The LLM picks a command name and its arguments (object names or numbers); it never
writes GeoGebra syntax. Each command has one or more overloads: the planner checks
the arguments against the figure, picks the first overload that fits, and builds the
GeoGebra command from the overload's template. Each overload also names the i18n
message spoken to the student.
"""

from dataclasses import dataclass
from typing import Literal

# What an object is, for argument checking. "line" covers lines, segments and rays.
Kind = Literal["point", "line", "circle", "polygon", "number"]
# A parameter accepts one kind, or "figure": anything that can be transformed.
Param = Literal["point", "line", "circle", "polygon", "number", "figure"]
FIGURE_KINDS: frozenset[Kind] = frozenset({"point", "line", "circle", "polygon"})

# GeoGebra object types (ggbApplet.getObjectType) by kind.
_GEOGEBRA_TYPES: dict[str, Kind] = {
    "point": "point",
    "line": "line",
    "segment": "line",
    "ray": "line",
    "circle": "circle",
    "polygon": "polygon",
    "triangle": "polygon",
    "quadrilateral": "polygon",
    "pentagon": "polygon",
    "hexagon": "polygon",
    "numeric": "number",
    "angle": "number",
}


def kind_of(geogebra_type: str) -> Kind | None:
    return _GEOGEBRA_TYPES.get(geogebra_type.lower())


@dataclass(frozen=True)
class Overload:
    params: tuple[Param, ...]
    # Kind of the created object; "same" for a transformation: the kind of its first argument.
    result: Kind | Literal["same"]
    # GeoGebra command; {0}, {1}... are the arguments, {all} all of them comma-separated.
    template: str
    message: str  # i18n key
    variadic: bool = False  # the last parameter may repeat

    def accepts_count(self, count: int) -> bool:
        if self.variadic:
            return count >= len(self.params)
        return count == len(self.params)

    def param(self, index: int) -> Param:
        return self.params[min(index, len(self.params) - 1)]


def _o(
    params: str,
    result: Kind | Literal["same"],
    template: str,
    message: str,
    *,
    variadic: bool = False,
) -> Overload:
    return Overload(tuple(params.split()), result, template, message, variadic)  # type: ignore[arg-type]


# Angle(A, B, C) can give the reflex angle; students expect the one below 180°.
_ANGLE = "If(Angle({0}, {1}, {2}) <= 180°, Angle({0}, {1}, {2}), Angle({2}, {1}, {0}))"

COMMANDS: dict[str, tuple[Overload, ...]] = {
    # Constructions.
    "Midpoint": (_o("point point", "point", "Midpoint({0}, {1})", "midpoint_created"),),
    "PerpendicularBisector": (
        _o("point point", "line", "PerpendicularBisector({0}, {1})", "bisector_created"),
    ),
    "AngleBisector": (
        _o("point point point", "line", "AngleBisector({0}, {1}, {2})", "angle_bisector_created"),
    ),
    "PerpendicularLine": (
        _o("point line", "line", "PerpendicularLine({0}, {1})", "perpendicular_created"),
    ),
    "ParallelLine": (_o("point line", "line", "Line({0}, {1})", "parallel_created"),),
    "Polygon": (
        _o("point point point", "polygon", "Polygon({all})", "polygon_created", variadic=True),
    ),
    "Intersect": (
        _o("line line", "point", "Intersect({0}, {1})", "intersection_created"),
        _o("circle line number", "point", "Intersect({0}, {1}, {2})", "intersection_created"),
        _o("line circle number", "point", "Intersect({0}, {1}, {2})", "intersection_created"),
        _o("circle circle number", "point", "Intersect({0}, {1}, {2})", "intersection_created"),
    ),
    # Transformations.
    "Reflect": (
        _o("figure point", "same", "Reflect({0}, {1})", "central_symmetry_created"),
        _o("figure line", "same", "Reflect({0}, {1})", "axial_symmetry_created"),
    ),
    "Translate": (
        _o("figure point point", "same", "Translate({0}, Vector({1}, {2}))", "translation_created"),
    ),
    "Rotate": (_o("figure number point", "same", "Rotate({0}, {1}°, {2})", "rotation_created"),),
    # Measures: the value is read in the browser once GeoGebra has computed it.
    "Distance": (_o("point point", "number", "Distance({0}, {1})", "distance_measured"),),
    "Angle": (_o("point point point", "number", _ANGLE, "angle_measured"),),
    "Area": (
        _o("polygon", "number", "Area({0})", "area_measured"),
        _o("circle", "number", "Area({0})", "area_measured"),
        _o("point point point", "number", "Area({all})", "area_measured", variadic=True),
    ),
    "Perimeter": (
        _o("polygon", "number", "Perimeter({0})", "perimeter_measured"),
        _o("circle", "number", "Perimeter({0})", "perimeter_measured"),
    ),
}

COMMAND_NAMES: tuple[str, ...] = tuple(COMMANDS)
MAX_ARGS = 12


def describe_commands() -> str:
    """One line per overload, for the action's description sent to the LLM."""
    lines = []
    for name, overloads in COMMANDS.items():
        for overload in overloads:
            params = ", ".join(overload.params) + (", ..." if overload.variadic else "")
            lines.append(f"{name}({params})")
    return "; ".join(lines)
