"""Geometry actions the LLM is allowed to request.

Each action is a Pydantic model exposed to the LLM as a tool: the class docstring
becomes the tool description and the fields become its parameters. Every tool
call is parsed back into one of these models, so nothing unvalidated ever
reaches GeoGebra.
"""

from typing import Annotated, Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from accessible_geometry.errors import InterpretationError

# GeoGebra labels: a letter, then letters, digits, underscores or primes (A, C1, A_1, A').
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_']{0,15}$"
COORDINATE_LIMIT = 1000.0

PointName = Annotated[
    str, Field(pattern=NAME_PATTERN, description="Name of a point, e.g. A, B, C1 or A'.")
]
ObjectName = Annotated[
    str, Field(pattern=NAME_PATTERN, description="Name of an object of the figure.")
]
Coordinate = Annotated[float, Field(ge=-COORDINATE_LIMIT, le=COORDINATE_LIMIT)]
Length = Annotated[float, Field(gt=0, le=COORDINATE_LIMIT)]
StepCount = Annotated[int, Field(ge=1, le=20, description="How many actions to undo or redo.")]


class GeometryAction(BaseModel):
    """Base class of all actions. Subclasses set `tool_name` and a docstring."""

    model_config = ConfigDict(extra="ignore")

    tool_name: ClassVar[str]


def _require_distinct(first: str, second: str) -> None:
    if first == second:
        raise ValueError(f"the two points must be different, got {first} twice")


class CreatePoint(GeometryAction):
    """Place a new point. Give x and y only if the student said the coordinates."""

    tool_name: ClassVar[str] = "create_point"

    name: PointName | None = Field(
        default=None, description="Point name. Omit it to use the next free letter."
    )
    x: Coordinate | None = Field(default=None, description="x coordinate (abscisse).")
    y: Coordinate | None = Field(default=None, description="y coordinate (ordonnée).")

    @model_validator(mode="after")
    def _coordinates_come_in_pairs(self) -> Self:
        if (self.x is None) != (self.y is None):
            raise ValueError("give both x and y, or neither")
        return self


class CreateSegment(GeometryAction):
    """Draw the segment [AB] between two existing points."""

    tool_name: ClassVar[str] = "create_segment"

    start: PointName
    end: PointName

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _require_distinct(self.start, self.end)
        return self


class CreateLine(GeometryAction):
    """Draw the line (AB), infinite in both directions, through two existing points."""

    tool_name: ClassVar[str] = "create_line"

    point1: PointName
    point2: PointName
    name: ObjectName | None = Field(default=None, description="Optional line name, e.g. d.")

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _require_distinct(self.point1, self.point2)
        return self


class CreateRay(GeometryAction):
    """Draw the ray [AB) (demi-droite) starting at `origin` and passing through `through`."""

    tool_name: ClassVar[str] = "create_ray"

    origin: PointName
    through: PointName
    name: ObjectName | None = Field(default=None, description="Optional ray name.")

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _require_distinct(self.origin, self.through)
        return self


class CreateCircle(GeometryAction):
    """Draw a circle from its center and either a radius or a point it passes through.

    Give exactly one of `radius` and `through`.
    """

    tool_name: ClassVar[str] = "create_circle"

    center: PointName
    radius: Length | None = Field(default=None, description="Radius length.")
    through: PointName | None = Field(default=None, description="A point on the circle.")
    name: ObjectName | None = Field(default=None, description="Optional circle name, e.g. c.")

    @model_validator(mode="after")
    def _radius_xor_through(self) -> Self:
        if (self.radius is None) == (self.through is None):
            raise ValueError("give exactly one of radius and through")
        if self.through is not None:
            _require_distinct(self.center, self.through)
        return self


class DeleteObject(GeometryAction):
    """Delete an object. Objects that depend on it are deleted too."""

    tool_name: ClassVar[str] = "delete_object"

    name: ObjectName


class Undo(GeometryAction):
    """Undo the last action(s) ("annule", "retour en arrière")."""

    tool_name: ClassVar[str] = "undo"

    steps: StepCount = 1


class Redo(GeometryAction):
    """Redo the last undone action(s) ("rétablis")."""

    tool_name: ClassVar[str] = "redo"

    steps: StepCount = 1


class AskClarification(GeometryAction):
    """Ask the student one short question when the request is ambiguous or impossible."""

    tool_name: ClassVar[str] = "ask_clarification"

    question: str = Field(min_length=1, max_length=300)


ACTION_TYPES: tuple[type[GeometryAction], ...] = (
    CreatePoint,
    CreateSegment,
    CreateLine,
    CreateRay,
    CreateCircle,
    DeleteObject,
    Undo,
    Redo,
    AskClarification,
)
ACTIONS_BY_TOOL: dict[str, type[GeometryAction]] = {a.tool_name: a for a in ACTION_TYPES}


def parse_tool_call(tool_name: str, arguments: str) -> GeometryAction:
    """Turn one LLM tool call (name + JSON arguments) into a validated action."""
    action_type = ACTIONS_BY_TOOL.get(tool_name)
    if action_type is None:
        raise InterpretationError(f"unknown tool {tool_name!r}")
    try:
        return action_type.model_validate_json(arguments or "{}")
    except ValidationError as exc:
        raise InterpretationError(f"invalid arguments for {tool_name}: {exc}") from exc


def tool_definitions() -> list[dict[str, Any]]:
    """JSON tool definitions in the OpenAI / Groq function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": action.tool_name,
                "description": " ".join((action.__doc__ or "").split()),
                "parameters": _simplify_schema(action.model_json_schema()),
            },
        }
        for action in ACTION_TYPES
    ]


def _simplify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic JSON schema easier for an LLM to follow.

    Drops titles and the top-level description (it is already the tool
    description), and turns `anyOf: [X, null]` into plain `X`: optional
    parameters are simply left out of `required`.
    """
    cleaned: dict[str, Any] = _strip(schema)
    cleaned.pop("description", None)
    return cleaned


def _strip(node: Any) -> Any:
    if isinstance(node, list):
        return [_strip(item) for item in node]
    if not isinstance(node, dict):
        return node
    variants = node.get("anyOf")
    if isinstance(variants, list) and {"type": "null"} in variants and len(variants) == 2:
        (inner,) = (v for v in variants if v != {"type": "null"})
        node = {**{k: v for k, v in node.items() if k != "anyOf"}, **inner}
    # A string-valued "title" is schema metadata; a dict-valued one would be a field named title.
    return {
        key: _strip(value)
        for key, value in node.items()
        if not (key == "title" and isinstance(value, str))
    }
