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
    "midpoint_created": {
        "fr": "Milieu {name} de [{a0}{a1}] placé.",
        "en": "Midpoint {name} of {a0}{a1} placed.",
    },
    "bisector_created": {
        "fr": "Médiatrice {name} de [{a0}{a1}] tracée.",
        "en": "Perpendicular bisector {name} of {a0}{a1} drawn.",
    },
    "angle_bisector_created": {
        "fr": "Bissectrice {name} de l'angle {a0}{a1}{a2} tracée.",
        "en": "Bisector {name} of angle {a0}{a1}{a2} drawn.",
    },
    "perpendicular_created": {
        "fr": "Perpendiculaire {name} à {a1} passant par {a0} tracée.",
        "en": "Perpendicular {name} to {a1} through {a0} drawn.",
    },
    "parallel_created": {
        "fr": "Parallèle {name} à {a1} passant par {a0} tracée.",
        "en": "Parallel {name} to {a1} through {a0} drawn.",
    },
    "polygon_created": {
        "fr": "Polygone {name} tracé.",
        "en": "Polygon {name} drawn.",
    },
    "intersection_created": {
        "fr": "Point {name}, intersection de {a0} et {a1}, placé.",
        "en": "Point {name}, intersection of {a0} and {a1}, placed.",
    },
    "central_symmetry_created": {
        "fr": "{name}, symétrique de {a0} par rapport au point {a1}, construit.",
        "en": "{name}, image of {a0} by the point reflection in {a1}, drawn.",
    },
    "axial_symmetry_created": {
        "fr": "{name}, symétrique de {a0} par rapport à la droite {a1}, construit.",
        "en": "{name}, reflection of {a0} in the line {a1}, drawn.",
    },
    "translation_created": {
        "fr": "{name}, image de {a0} par la translation qui transforme {a1} en {a2}, construit.",
        "en": "{name}, image of {a0} by the translation taking {a1} to {a2}, drawn.",
    },
    "rotation_created": {
        "fr": "{name}, image de {a0} par la rotation de centre {a2} et d'angle {a1}°, construit.",
        "en": "{name}, image of {a0} by the rotation with center {a2} and angle {a1}°, drawn.",
    },
    "distance_measured": {
        "fr": "La longueur {a0}{a1} est {value}.",
        "en": "The length {a0}{a1} is {value}.",
    },
    "angle_measured": {
        "fr": "L'angle {a0}{a1}{a2} mesure {value}°.",
        "en": "Angle {a0}{a1}{a2} measures {value}°.",
    },
    "area_measured": {
        "fr": "L'aire de {all} est {value}.",
        "en": "The area of {all} is {value}.",
    },
    "perimeter_measured": {
        "fr": "Le périmètre de {all} est {value}.",
        "en": "The perimeter of {all} is {value}.",
    },
    "renamed": {
        "fr": "{name} renommé en {new_name}.",
        "en": "{name} renamed {new_name}.",
    },
    "point_moved": {
        "fr": "Point {name} déplacé en ({x} ; {y}).",
        "en": "Point {name} moved to ({x}, {y}).",
    },
    "object_deleted": {
        "fr": "{name} supprimé.",
        "en": "{name} deleted.",
    },
    "figure_cleared": {
        "fr": "Figure effacée. Dites « annule » pour la retrouver.",
        "en": 'Figure cleared. Say "undo" to bring it back.',
    },
    "figure_already_empty": {
        "fr": "La figure est déjà vide.",
        "en": "The figure is already empty.",
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
    "point_not_free": {
        "fr": "{name} dépend d'autres objets : on ne peut pas le déplacer.",
        "en": "{name} depends on other objects, so it cannot be moved.",
    },
    "wrong_arguments": {
        "fr": "Cette construction ne s'applique pas à {args}.",
        "en": "This construction does not apply to {args}.",
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
