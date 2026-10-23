# Accessible Geometry

Voice-controlled [GeoGebra](https://www.geogebra.org/) for middle-school students
(French *collège*, 6e–3e) who cannot use a mouse or a keyboard. Students build
geometric figures by speaking, in French or English:

> « Place le point A en 0 0 et le point B en 4 0, puis trace le segment [AB]. »
> « Trace le cercle de centre A passant par B. »
> « Annule. »

The app carries out the request, shows it in GeoGebra and confirms it out loud.

> **Status:** proof of concept, milestone 1 (core voice loop). School project, non-commercial.

## How it works

```
Browser                                    Python backend (FastAPI)
┌───────────────────────────┐              ┌──────────────────────────────────────┐
│ GeoGebra applet           │  audio +     │ 1. Speech-to-text  (Whisper on Groq) │
│ Push-to-talk (Space/button)│─ figure ───▶│ 2. Interpretation  (LLM tool calls)  │
│ Runs GeoGebra commands    │              │ 3. Validation + translation to       │
│ Speaks the feedback       │◀─ steps + ───│    GeoGebra commands (planner)       │
└───────────────────────────┘   message    └──────────────────────────────────────┘
```

Design choices:

- **The LLM never writes GeoGebra commands.** It may only call a fixed set of tools
  (`create_point`, `create_segment`, `create_circle`, `undo`...), defined as Pydantic
  models in [`geometry/actions.py`](src/accessible_geometry/geometry/actions.py).
  The [planner](src/accessible_geometry/geometry/planner.py) checks every call against
  the current figure and translates it into GeoGebra commands. This keeps the system
  predictable, safe and testable.
- **All or nothing.** If any part of a request cannot be carried out, nothing is changed
  and the student is told why. Each spoken request is a single undo step.
- **Feedback is deterministic.** Confirmation messages are generated from templates in
  [`i18n.py`](src/accessible_geometry/i18n.py), not written by the LLM.
- **When in doubt, ask.** Ambiguous requests produce a short clarification question
  instead of a guess.

## Getting started

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), a recent Chrome, Edge or
Firefox, and a free [Groq API key](https://console.groq.com/keys).

```bash
uv sync                    # install dependencies into .venv
cp .env.example .env       # then put your key in GROQ_API_KEY
uv run accessible-geometry # http://127.0.0.1:8000
```

For development with auto-reload:

```bash
uv run uvicorn --factory accessible_geometry.main:create_app --reload
```

The app starts without an API key (the page and GeoGebra load), but commands are
disabled and a warning banner is shown.

### Using it

- **Space bar:** hold it while speaking, release to send.
- **Microphone button:** press once to start, once more to send.
- **Text field:** type a command instead of speaking (handy for testing).

## Development

```bash
uv run pytest              # tests (no API key or network needed)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # type check (strict)
```

The tests replace Groq with fakes ([`tests/fakes.py`](tests/fakes.py)), so they run
offline. CI runs all of the above on every push ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

### Project layout

```
src/accessible_geometry/
├── main.py              # app factory, `accessible-geometry` entry point
├── config.py            # settings from environment / .env
├── service.py           # pipeline: speech → interpretation → plan
├── i18n.py              # French / English messages
├── api/routes.py        # /api/health, /api/command, /api/voice
├── speech/transcriber.py# Whisper (Groq) speech-to-text
├── llm/
│   ├── interpreter.py   # LLM tool calling (Groq)
│   └── prompts.py       # system prompt + figure description
├── geometry/
│   ├── actions.py       # the tools the LLM may call (Pydantic models)
│   ├── planner.py       # validation + translation to GeoGebra commands
│   └── state.py         # figure snapshot sent by the browser
└── static/              # front end: HTML, CSS, JS modules (no build step)
tests/
```

### Adding a new geometry action

1. Add a Pydantic model in `geometry/actions.py` (its docstring becomes the tool
   description) and register it in `ACTION_TYPES`.
2. Handle it in `geometry/planner.py` and add its messages to `i18n.py`.
3. Add vocabulary examples to `llm/prompts.py` if needed.
4. Add tests.

## Roadmap

1. ~~**Core loop:** push-to-talk, points, segments, lines, rays, circles, delete, undo/redo.~~
2. **Collège vocabulary:** midpoints, perpendicular bisectors, angle bisectors,
   parallels and perpendiculars, polygons, symmetries, measurements, renaming and moving points.
3. **Exercises:** YAML-defined exercises, checked automatically with GeoGebra, with hints.
4. **Quality:** a test set of real FR/EN spoken phrases checked against expected actions.

## License

This project's code is released under the [MIT License](LICENSE).

The GeoGebra apps it loads from geogebra.org are not covered by this license: they are
free for [non-commercial use](https://www.geogebra.org/license) only.
