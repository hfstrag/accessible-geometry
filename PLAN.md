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

Stopgap to revisit in milestone 2: a midpoint is a free point at computed coordinates,
not a GeoGebra `Midpoint`, so it would not follow A or B once points can be moved.
The view is not checked: the prompt keeps figures in x -5..8, y -4..5, but whether that
fits GeoGebra's default view on a school screen has not been checked in the browser.

### 2. Milestone 2: collège vocabulary

Midpoints, perpendicular bisectors, angle bisectors, parallel and perpendicular lines,
polygons, symmetries (central and axial), measuring lengths, angles and areas, renaming
and moving points.

- [ ] **Open question:** should the LLM also be allowed to use a whitelisted set of
      GeoGebra commands (`Midpoint`, `PerpendicularBisector`, `Polygon`...), validated by
      the server? This covers many more constructions quickly, but spoken feedback for
      those commands would be less precise.

### 3. Milestone 3: exercises

Exercises defined in YAML: a statement, success checks run in GeoGebra (`ArePerpendicular`,
`AreCollinear`, lengths, angles...), and hints. The LLM words the hints but never builds
the answer.

### 4. Milestone 4: quality

Error handling, a larger FR/EN phrase test set, and testing with real students and
teachers.

## Known limitations

- Free-tier Groq rate limits: commands sent back to back can wait 10–30 s.
- The conversation history is lost when the page reloads.
- The browser side (GeoGebra, microphone, speech) has no automated tests.
