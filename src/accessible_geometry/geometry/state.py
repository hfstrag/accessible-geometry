"""Snapshot of the GeoGebra construction, sent by the browser with every command."""

from pydantic import BaseModel, Field, field_validator


class GeoObject(BaseModel):
    """One object of the construction, as reported by the GeoGebra JS API."""

    name: str = Field(max_length=64)
    type: str = Field(max_length=32, description="GeoGebra object type, e.g. 'point', 'segment'.")
    definition: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, max_length=500)
    x: float | None = None
    y: float | None = None

    @field_validator("definition")
    @classmethod
    def _round_brackets(cls, definition: str | None) -> str | None:
        """GeoGebra writes "Line[A, B]"; the actions and the LLM prompt use "Line(A, B)"."""
        return definition.replace("[", "(").replace("]", ")") if definition else definition

    @property
    def is_point(self) -> bool:
        return self.type == "point"


class ConstructionState(BaseModel):
    objects: list[GeoObject] = Field(default_factory=list, max_length=500)

    def find(self, name: str) -> GeoObject | None:
        return next((obj for obj in self.objects if obj.name == name), None)
