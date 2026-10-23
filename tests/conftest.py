import pytest

from accessible_geometry.geometry.state import ConstructionState, GeoObject


@pytest.fixture
def triangle_points() -> ConstructionState:
    """A figure with points A(0, 0), B(4, 0), C(0, 3) and segment f = [AB]."""
    return ConstructionState(
        objects=[
            GeoObject(name="A", type="point", definition="", value="(0, 0)", x=0, y=0),
            GeoObject(name="B", type="point", definition="", value="(4, 0)", x=4, y=0),
            GeoObject(name="C", type="point", definition="", value="(0, 3)", x=0, y=3),
            GeoObject(name="f", type="segment", definition="Segment(A, B)", value="4"),
        ]
    )
