"""Snapshot of the GeoGebra construction, sent by the browser with every command."""

from pydantic import BaseModel, Field


class GeoObject(BaseModel):
    """One object of the construction, as reported by the GeoGebra JS API."""

    name: str = Field(max_length=64)
    type: str = Field(max_length=32, description="GeoGebra object type, e.g. 'point', 'segment'.")
    definition: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, max_length=500)
    x: float | None = None
    y: float | None = None

    @property
    def is_point(self) -> bool:
        return self.type == "point"


class ConstructionState(BaseModel):
    objects: list[GeoObject] = Field(default_factory=list, max_length=500)

    def find(self, name: str) -> GeoObject | None:
        return next((obj for obj in self.objects if obj.name == name), None)
