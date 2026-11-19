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

### 1. Make the LLM take initiative (in progress, awaiting go-ahead)

Probing showed the model asks questions instead of acting ("trace un triangle", "place
trois points", "cercle de rayon 2", "milieu de AB"), and "carré ABCD de côté 4" drew a
shape that is not a square. Causes: the prompt says to never invent coordinates and to
ask when anything is ambiguous, there are no worked examples, and some actions are missing.

- [ ] Prompt: choose names and positions by itself, compute exact coordinates for regular
      shapes, create missing points (e.g. a circle's center), and say what it chose. Ask
      only when the request cannot be carried out. This reverses the earlier "ask rather
      than guess" default.
- [ ] Add 6–8 worked FR/EN examples to the system prompt.
- [ ] Phrase test set: phrases with expected outcomes (e.g. `tests/eval/phrases.yaml`) and a
      script that runs them against the real model and gives a score. Kept out of pytest
      and CI because it needs the API key.

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
