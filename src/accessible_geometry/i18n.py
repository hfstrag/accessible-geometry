"""User-facing messages in French and English.

Messages are shown on screen and read aloud, so they stay short and plain.
"""

from typing import Literal

Language = Literal["fr", "en"]

_MESSAGES: dict[str, dict[Language, str]] = {
    "point_created": {
        "fr": "Point {name} placé en ({x} ; {y}).",
        "en": "Point {name} placed at ({x}, {y}).",
    },
    "segment_created": {
        "fr": "Segment [{a}{b}] tracé.",
        "en": "Segment {a}{b} drawn.",
    },
    "line_created": {
        "fr": "Droite ({a}{b}) tracée.",
        "en": "Line {a}{b} drawn.",
    },
    "ray_created": {
        "fr": "Demi-droite [{a}{b}) tracée.",
        "en": "Ray {a}{b} drawn.",
    },
    "circle_radius_created": {
        "fr": "Cercle de centre {center} et de rayon {radius} tracé.",
        "en": "Circle with center {center} and radius {radius} drawn.",
    },
    "circle_through_created": {
        "fr": "Cercle de centre {center} passant par {through} tracé.",
        "en": "Circle with center {center} through {through} drawn.",
    },
    "object_deleted": {
        "fr": "{name} supprimé.",
        "en": "{name} deleted.",
    },
    "undone": {
        "fr": "Dernière action annulée.",
        "en": "Last action undone.",
    },
    "undone_many": {
        "fr": "{count} actions annulées.",
        "en": "{count} actions undone.",
    },
    "redone": {
        "fr": "Action rétablie.",
        "en": "Action redone.",
    },
    "redone_many": {
        "fr": "{count} actions rétablies.",
        "en": "{count} actions redone.",
    },
    "unknown_object": {
        "fr": "Je ne trouve pas {name} dans la figure.",
        "en": "I can't find {name} in the figure.",
    },
    "not_a_point": {
        "fr": "{name} n'est pas un point.",
        "en": "{name} is not a point.",
    },
    "name_taken": {
        "fr": "Le nom {name} est déjà utilisé.",
        "en": "The name {name} is already used.",
    },
    "not_understood": {
        "fr": "Je n'ai pas compris. Pouvez-vous reformuler ?",
        "en": "I didn't understand. Could you rephrase?",
    },
    "nothing_heard": {
        "fr": "Je n'ai rien entendu. Pouvez-vous répéter ?",
        "en": "I didn't hear anything. Could you say it again?",
    },
}


def translate(key: str, language: Language, **params: object) -> str:
    """Return the message `key` in `language`, formatted with `params`."""
    return _MESSAGES[key][language].format(**params)


def format_number(value: float, language: Language) -> str:
    """Format a number for display and speech: at most 2 decimals, no trailing zeros.

    French uses a decimal comma ("1,5"), English a decimal point ("1.5").
    """
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text.replace(".", ",") if language == "fr" else text
