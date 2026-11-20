# Plan

## Goal

A strong MVP that lets middle-school students who cannot use a mouse or keyboard build
geometry figures with their voice, in French or English. It offers two modes: a free
sandbox, and exercises with automatic checking. It will run on school computers later; for
now it is a proof of concept.

## Decisions made

| Topic | Decision |
|---|---|
| Users | Students using only their voice (motor disabilities); FR + EN; collège 6e–3e |
| Input | Push-to-talk (Space held, or button pressed twice) |
| Stack | Python (FastAPI) + thin JS; GeoGebra Apps API loaded from geogebra.org |
| AI | Groq: Whisper (`whisper-large-v3-turbo`) for speech, `openai/gpt-oss-120b` for interpretation |
| LLM output | One `apply_actions` call per command with a list of validated actions |
| Memory | Browser sends the last 8 exchanges with each command |
| Sandbox mode | The app does what the student says |
| Exercise mode | The app must not build the solution for the student |
| Fine-tuning | Not now: the problems come from the prompt and the missing actions |

## Status

**Milestone 1 (done):** core voice loop. Points, segments, lines, rays, circles, delete,
undo and redo; spoken feedback; dev logging; 73 offline tests; CI.

## Next

### 1. Make the LLM take initiative (done)

Probing showed the model asked questions instead of acting ("trace un triangle", "place
trois points", "cercle de rayon 2", "milieu de AB"), and "carré ABCD de côté 4" drew a
shape that was not a square.

- [x] Prompt: the model chooses names (next free letters, O for a center, I for a
      midpoint) and positions (near the origin, sides of 3–5), computes exact coordinates
      for named shapes, and creates missing points. It asks only when it cannot act. This
      reverses the earlier "ask rather than guess" default. The spoken feedback already
      gives the chosen names and coordinates.
- [x] 8 worked FR/EN examples in the system prompt.
- [x] Phrase test set `tests/eval/phrases.yaml` (27 cases) and runner
      `uv run python -m tests.eval.run_eval`: 27/27 with `openai/gpt-oss-120b`
      (2026-11-19, ~8 min because of rate limits). Kept out of CI; the runner itself is
      tested offline in `tests/test_eval_runner.py`.

The view is not checked: the prompt keeps figures in x -5..8, y -4..5, but whether that
fits GeoGebra's default view on a school screen has not been checked in the browser.

### 2. Milestone 2: collège vocabulary (done, pending browser testing by a person)

Decision (2026-11-20): the LLM may request **whitelisted GeoGebra commands** through one
`geogebra_command` action. It picks a command name and its arguments (object names or
numbers); `geometry/commands.py` lists each command's typed overloads (point, line,
circle, polygon, number, figure), and the planner checks the arguments against the
figure and writes the GeoGebra syntax. Every overload has its own FR/EN message, so the
feedback stays precise.

- [x] Constructions: Midpoint, PerpendicularBisector, AngleBisector, PerpendicularLine,
      ParallelLine, Polygon, Intersect (lines; circles with an index 1 or 2).
- [x] Transformations: Reflect (central and axial symmetry), Translate, Rotate. Images
      are named A', A''...
- [x] Measures: Distance, Angle (never reflex), Area, Perimeter. The value is only known
      in GeoGebra: the message holds `{{name}}`, filled in by the browser.
- [x] `rename_object` and `move_point` actions (only free points can move).
- [x] Midpoints are real GeoGebra `Midpoint`s now (the milestone 1 stopgap is gone).
- [x] Checked in a real browser with the GeoGebra API (2026-11-20). That check found
      and fixed: `Rename`/`SetCoords` return false although they work; a labelled
      command silently redefines an existing object (the browser now refuses it, and
      the planner reserves the names GeoGebra gives to polygon sides and images);
      definitions come as `Line[A, B]` and free points as `(0, 0)`.
- [ ] Phrase test set: 18 milestone 2 phrases added to `tests/eval/phrases.yaml` (45 in
      all). The run was stopped on Groq rate limits before it finished: run it again with
      a fresh quota (`uv run python -m tests.eval.run_eval`), tune the prompt on failures.
- [ ] Try it by voice in the app: the full loop (speech, feedback, undo) with the new
      commands has not been tested by a person yet.

### 3. Milestone 3: exercises

Exercises defined in YAML: a statement, success checks run in GeoGebra (`ArePerpendicular`,
`AreCollinear`, lengths, angles...), and hints. The LLM words the hints but never builds
the answer.

### 4. Milestone 4: quality

Error handling, a larger FR/EN phrase test set, and testing with real students and
teachers.

## Known limitations

- Free-tier Groq rate limits: the free tier allows 8,000 tokens per minute and a
  command now costs about 5,800 (the prompt and tool schema grew by about 50% in
  milestone 2), so commands sent back to back can wait up to a minute. The prompt
  could be trimmed if this becomes a problem.
- The conversation history is lost when the page reloads.
- The browser side (GeoGebra, microphone, speech) has no automated tests.
