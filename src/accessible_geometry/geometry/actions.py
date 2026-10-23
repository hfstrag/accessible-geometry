"""Geometry actions the LLM is allowed to request.

Each action is a Pydantic model. The LLM gets a single tool, `apply_actions`,
whose argument is the ordered list of actions for the whole request: one LLM
call per command. In that list, each action is an object whose `action` key is
the model's `action_name`, whose description is the class docstring, and whose
other keys are the model's fields. Every item is parsed back into one of these
models, so nothing unvalidated ever reaches GeoGebra.
"""

import json
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
    """Base class of all actions. Subclasses set `action_name` and a docstring."""

    model_config = ConfigDict(extra="ignore")

    action_name: ClassVar[str]


def _require_distinct(first: str, second: str) -> None:
    if first == second:
        raise ValueError(f"the two points must be different, got {first} twice")


class CreatePoint(GeometryAction):
    """Place a new point. Give x and y only if the student said the coordinates."""

    action_name: ClassVar[str] = "create_point"

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

    action_name: ClassVar[str] = "create_segment"

    start: PointName
    end: PointName

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _require_distinct(self.start, self.end)
        return self


class CreateLine(GeometryAction):
    """Draw the line (AB), infinite in both directions, through two existing points."""

    action_name: ClassVar[str] = "create_line"

    point1: PointName
    point2: PointName
    name: ObjectName | None = Field(default=None, description="Optional line name, e.g. d.")

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _require_distinct(self.point1, self.point2)
        return self


class CreateRay(GeometryAction):
    """Draw the ray [AB) (demi-droite) starting at `origin` and passing through `through`."""

    action_name: ClassVar[str] = "create_ray"

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

    action_name: ClassVar[str] = "create_circle"

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

    action_name: ClassVar[str] = "delete_object"

    name: ObjectName


class Undo(GeometryAction):
    """Undo the last action(s) ("annule", "retour en arrière")."""

    action_name: ClassVar[str] = "undo"

    steps: StepCount = 1


class Redo(GeometryAction):
    """Redo the last undone action(s) ("rétablis")."""

    action_name: ClassVar[str] = "redo"

    steps: StepCount = 1


class AskClarification(GeometryAction):
    """Ask the student one short question when the request is ambiguous or impossible."""

    action_name: ClassVar[str] = "ask_clarification"

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
ACTIONS_BY_NAME: dict[str, type[GeometryAction]] = {a.action_name: a for a in ACTION_TYPES}


TOOL_NAME = "apply_actions"
MAX_ACTIONS = 20


def parse_tool_call(tool_name: str, arguments: str) -> list[GeometryAction]:
    """Turn one `apply_actions` call (JSON arguments) into validated actions.

    Errors name the faulty items so that the LLM can correct them.
    """
    if tool_name != TOOL_NAME:
        raise InterpretationError(f"unknown tool {tool_name!r}, the only tool is {TOOL_NAME}")
    try:
        payload = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise InterpretationError(f"arguments are not valid JSON: {exc}") from exc
    items = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise InterpretationError("'actions' must be a non-empty list")
    if len(items) > MAX_ACTIONS:
        raise InterpretationError(f"at most {MAX_ACTIONS} actions per request")

    actions: list[GeometryAction] = []
    errors: list[str] = []
    for index, item in enumerate(items, start=1):
        try:
            actions.append(_parse_item(item))
        except InterpretationError as exc:
            errors.append(f"action {index}: {exc}")
    if errors:
        raise InterpretationError("; ".join(errors))
    return actions


def _parse_item(item: Any) -> GeometryAction:
    if not isinstance(item, dict):
        raise InterpretationError("must be an object")
    name = item.get("action")
    action_type = ACTIONS_BY_NAME.get(name) if isinstance(name, str) else None
    if action_type is None:
        raise InterpretationError(f"unknown action {name!r}")
    try:
        return action_type.model_validate({k: v for k, v in item.items() if k != "action"})
    except ValidationError as exc:
        details = ", ".join(
            f"{'.'.join(map(str, error['loc'])) or 'arguments'}: {error['msg']}"
            for error in exc.errors()
        )
        raise InterpretationError(f"invalid {name} ({details})") from exc


def tool_definitions() -> list[dict[str, Any]]:
    """The `apply_actions` tool, in the OpenAI / Groq function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": (
                    "Apply the student's whole request to the figure: "
                    "the list of actions, in order."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actions": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": MAX_ACTIONS,
                            "items": {"anyOf": [_action_schema(a) for a in ACTION_TYPES]},
                        }
                    },
                    "required": ["actions"],
                },
            },
        }
    ]


def _action_schema(action: type[GeometryAction]) -> dict[str, Any]:
    """Schema of one item of the `actions` list, tagged by its `action` key.

    Simplified for the LLM, to save prompt tokens: `anyOf: [X, null]` becomes
    plain `X` (optional parameters are simply left out of `required`), and
    titles, defaults and constraints are dropped. Constraints are still
    enforced by Pydantic when parsing, and violations are sent back to the LLM.
    """
    schema: dict[str, Any] = _strip(action.model_json_schema())
    return {
        "type": "object",
        "description": " ".join((action.__doc__ or "").split()),
        "properties": {"action": {"const": action.action_name}, **schema.get("properties", {})},
        "required": ["action", *schema.get("required", [])],
    }


def _strip(node: Any) -> Any:
    if isinstance(node, list):
        return [_strip(item) for item in node]
    if not isinstance(node, dict):
        return node
    variants = node.get("anyOf")
    if isinstance(variants, list) and {"type": "null"} in variants and len(variants) == 2:
        (inner,) = (v for v in variants if v != {"type": "null"})
        node = {**{k: v for k, v in node.items() if k != "anyOf"}, **inner}
    # Keywords hold scalars; a dict value under the same key would be a field with that name.
    return {
        key: _strip(value)
        for key, value in node.items()
        if not (key in _OMITTED_KEYWORDS and not isinstance(value, dict))
    }


_OMITTED_KEYWORDS = {
    "title",
    "default",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
}
