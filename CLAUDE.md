# CLAUDE.md

Voice-controlled GeoGebra for French *collège* students (6e–3e) with disabilities who
cannot use a mouse or keyboard. School project, non-commercial, MIT-licensed.
Read [PLAN.md](PLAN.md) for the roadmap, current status and open decisions.

## Commands

```bash
uv sync                                                    # install
uv run accessible-geometry                                 # run on http://127.0.0.1:8000
uv run uvicorn --factory accessible_geometry.main:create_app --reload   # dev server
uv run pytest                                              # tests (offline, no API key)
uv run ruff check . && uv run ruff format .                # lint + format
uv run mypy                                                # strict type check
uv run python -m tests.eval.run_eval [ids]                 # phrase eval, real Groq (key needed)
```

Run pytest, ruff and mypy before every commit; CI (`.github/workflows/ci.yml`) runs all three
on Python 3.12. Local Python is 3.14; `requires-python >= 3.11`.

`.env` holds `GROQ_API_KEY` and is git-ignored: never read, print or commit it.
`.env.example` documents the settings. `LOG_LEVEL=debug` logs the full LLM prompt, the
model's reasoning, the raw tool calls and the GeoGebra steps.

## Architecture

Browser (thin JS, no build step) ↔ Python backend (FastAPI), both in `src/accessible_geometry/`.

1. Browser records audio (push-to-talk: hold Space, or press the button twice) and sends it
   with a snapshot of the GeoGebra figure and the last 8 exchanges (`conversation.py`).
2. `speech/transcriber.py`: Whisper on Groq, with a geometry vocabulary prompt.
3. `llm/interpreter.py`: one LLM call per command. The model has a single tool,
   `apply_actions`, taking the ordered list of actions; invalid items are sent back with
   the error (max 3 attempts). `llm/prompts.py` holds the system prompt.
4. `geometry/actions.py`: the actions the LLM may request, as Pydantic models (docstring =
   description sent to the LLM). The LLM-facing schema is stripped of patterns/bounds/defaults
   to save tokens; Pydantic still enforces them.
5. `geometry/planner.py`: validates actions against the figure and translates them to
   GeoGebra commands. All-or-nothing: any error rejects the whole request.
6. Browser runs the steps with the GeoGebra Apps API (`static/js/geogebra.js`), rolls back
   on failure, makes each request one undo step, and speaks the feedback.

## Design rules

- The LLM never writes raw GeoGebra commands: it picks validated actions and the planner
  writes the commands.
- Feedback messages come from templates in `i18n.py` (FR + EN), not from the LLM.
- Every user-facing string exists in French and English.
- The tests never call Groq: use the fakes in `tests/fakes.py`, or the fake Groq client in
  `tests/test_interpreter.py`.
- To add an action: model in `actions.py` + register in `ACTION_TYPES`, handle it in
  `planner.py`, messages in `i18n.py`, vocabulary in `prompts.py`, tests.

## Working with the user

- Python preferred; keep JavaScript minimal.
- Ask before committing or pushing; the user asks for those explicitly.
- Free-tier Groq rate limits (HTTP 429, retried by the SDK) are expected and accepted.
- To check model behaviour, run the server with `LOG_LEVEL=debug` and send typed commands to
  `POST /api/command`. Send JSON from a Python script, not curl in bash: accented characters
  get corrupted on this Windows machine.
