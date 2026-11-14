<div align="center">

# shorts-studio

**The local video studio that turns a single sentence into a publish-ready video.**
Motion design, batch production, footage editing, voice-over, captions and an AI assistant —
all on your machine, with no mandatory cloud and nothing done behind your back.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-467%20passed-brightgreen.svg)](#tests--verification)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#tech-stack)
[![Node](https://img.shields.io/badge/node-22-green.svg)](#tech-stack)
[![Remotion](https://img.shields.io/badge/Remotion-4.0.539-ff69b4.svg)](#tech-stack)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688.svg)](#tech-stack)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](#tech-stack)
[![Local first](https://img.shields.io/badge/local--first-no%20mandatory%20cloud-orange.svg)](#the-4-laws-of-the-studio)

*Web interface · `127.0.0.1` server · a single launcher: `start_web.bat`*

</div>

---

## In one sentence

> You describe the video you want. The assistant prepares the project, the autopilot renders it
> to MP4, the studio spins it into 200 variants from a CSV, assembles real footage edits,
> captions it, derives social formats and delivers it to the client as a ZIP.
> **You keep control of every sensitive click.**

`shorts-studio` (folder `youtube_clipper`) is a **complete, local, self-contained video production
studio**. It brings together in a single web app what is usually scattered across After Effects,
a captioning tool, a TTS engine, a batch script and an AI assistant: a visual editor, a deterministic
render engine, a production queue, an assistant that knows the studio inside out, and a commercial
delivery pipeline.

---

## An original project, fully remodeled

`shorts-studio` is **my project: my architecture, my code, my direction**. Remotion and OpenMontage
were starting points — one as a render engine, the other as a production grammar — but
**everything was remodeled, re-architected and rewritten** into a coherent studio that is wholly mine:

- the **v2 project format** and its deterministic resolution were designed for this studio;
- the **25 effects**, the caption engine, the voice-over, the B-roll and the social formats are
  home-grown implementations;
- the **AI assistant**, its proposal contract, its 32 tools and its autopilot are written from
  scratch, with no heavy AI framework;
- the **footage editing engine** (EDL contract + three-pass FFmpeg assembly) is an original
  implementation: no executable code from OpenMontage is copied.

Remotion remains a third-party library used under its own license; the OpenMontage grammar is kept
only as **read-only, local** documentation reference (see [License](#license)). The studio itself is
an original, proprietary work — not a wrapper, not a copy.

---

## Table of contents

- [An original project, fully remodeled](#an-original-project-fully-remodeled)
- [Why this studio?](#why-this-studio)
- [What you can do](#what-you-can-do)
- [Autopilot: one request → one MP4](#autopilot-one-request--one-mp4)
- [The AI assistant: it proposes, you apply](#the-ai-assistant-it-proposes-you-apply)
- [Footage editing: EDL → FFmpeg](#footage-editing-edl--ffmpeg)
- [The 4 laws of the studio](#the-4-laws-of-the-studio)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Security](#security)
- [Tests & verification](#tests--verification)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)
- [License](#license)
- [Full documentation](#full-documentation)

---

## Why this studio?

What sets `shorts-studio` apart from yet another "AI video generator":

| Strength | What it actually changes |
| --- | --- |
| **Original, proprietary work** | Architecture, v2 format, effects, assistant, EDL/FFmpeg engine: everything is designed and rewritten for this studio. Remotion and OpenMontage are remodeled foundations — not the product. |
| **Local-first, no mandatory cloud** | Everything runs on `127.0.0.1`. Your rushes, your text, your API keys never leave the machine. No account, no subscription, no telemetry. The studio stays **fully usable even with the LLM server turned off**. |
| **The plan you see is exactly what gets rendered** | The Remotion Player preview and the CLI render share **the same composition**. No "that's not what was on screen" surprise. A single render entry point, a single engine. |
| **The AI proposes, the human applies** | The assistant **never** triggers a render, a deletion, a batch or a download without a click. Every sensitive action goes through a confirmation token and a freshness re-check. |
| **Deterministic and reproducible** | The `resolved` block (frames, animation windows, fonts, seed) is computed server-side, never by the LLM. Same project + same seed = same video, frame for frame. |
| **No heavy dependency installed on the sly** | No LangChain, no OpenAI SDK, no ORM, no Docker. The assistant speaks the OpenAI-compatible API with raw `httpx`. Local Whisper is **detected, never installed**. |
| **A real footage bridge, not a gimmick** | Real editing (rushes, transitions, music, grading) goes through a closed EDL contract then FFmpeg. Remotion stays the motion-design engine. Each engine does what it does best. |
| **Built for commercial delivery** | Client brand packs, captions aligned to the rendered frames, thumbnails, metadata, manifest, ready-to-send ZIP. The studio produces a **deliverable**, not just an MP4. |
| **467 tests, real measurements** | Every guardrail is covered by a test. The advertised performance is **measured on this machine**, not inferred from a model name. |

---

## What you can do

The studio is organized into **five axes** (plus a legacy of kept tools), reachable through a grouped
navigation of **11 pages** and a command palette (`Ctrl+K`).

| Axis | The question it answers | Page | Engine |
| --- | --- | --- | --- |
| **DESIGN** | "How should my video be made?" — scenes, layers, text, fonts, colors, animations, audio, frame, client brand. | `/design` | Remotion |
| **PRODUCTION** | "How do I make 200 without opening the editor?" — template + CSV + media folders → plan → render queue. | `/production` | Remotion, in series |
| **HIGHLIGHTS** | "What is worth a clip in this source?" — Whisper transcription, scored and **explained** windows, then on click a captioned project. | `/moments` | Whisper + FFmpeg + Remotion |
| **DELIVERY** | "How do I send it to the client?" — a rendered batch becomes a ZIP: MP4, `.srt`, thumbnails, metadata, manifest, `LISEZ-MOI.txt`. | `/delivery` | `zipfile` + FFmpeg |
| **AI ASSISTANT** | "Tell me what you want, I'll prepare the project or the mapping." — global drawer present on every page (`Ctrl+I`). | everywhere | Local LLM / Gemini / Groq |
| *Legacy* | Earlier tools kept and wired to the web: YouTube Clips, Podcast, Shorts v1, Projects. | `/clips` `/podcast` `/short-videos` `/projects` | yt-dlp + Groq + FFmpeg |

### The capabilities that make the difference

- **25 motion-design effects** rendered with no extra package (Transform/CSS, SVG filters, masks,
  2D canvas, `@remotion/paths`): transitions, grading, parallax, plasma, chroma key, audio-reactive…
  Each effect has its settings and bounds, known to both the editor **and** the assistant.
- **5 font families** on disk under SIL OFL license (Anton, Archivo Black, Inter, Playfair Display,
  Space Grotesk), measured before rendering to flag any overflow.
- **Local voice-over**: a catalog of **234 voices, 53 languages** (Piper + Kokoro), offline synthesis.
  Voices are verified and their licenses recorded — nothing is downloaded without your click.
- **Kinetic captions aligned to the voice**: a "light" forced alignment reads the voice-over WAV
  (standard library only, no ASR) and pins each word to the frame. Deterministic.
- **Automatic B-roll**: the engine matches a scene's words against already-imported media and places
  a relevant visual — **with no LLM at all**, best-effort, never over a chosen background.
- **Image generation** via Pollinations (public API, **no key**): the image comes back locally and
  becomes a normal `media://<id>` media, assignable through the already-validated operations.
- **Derived social formats**: from the 9:16 master, the studio derives 1:1 and 16:9 by centered
  FFmpeg cropping, **with no Remotion re-render**.
- **Client brand packs**: what repeats from one video to the next (theme, logo, music, allowed
  templates) applied to a project or a whole batch — never touching scenes or text.

---

## Autopilot: one request → one MP4

Autopilot is the "autonomous director" mode. **A single LLM call** produces a complete, validated
plan; after that, **everything is deterministic, with no further call**:

```
one request
    │
    ▼  1 LLM call → validated plan (autopilot_plan)
┌─────────────────────────────────────────────────────────┐
│  SCRIPT     text applied (validated operations)           │
│  DESIGN     staging + effects + automatic B-roll          │
│  VOICE-OVER TTS synthesis + caption alignment             │
│  EXPORT     MP4 render + optional technical audit         │
└─────────────────────────────────────────────────────────┘
    │
    ▼  an MP4, aligned captions, a thumbnail
```

What makes autopilot robust:

- **Auto-resume**: every transition is persisted to disk (`projects/autopilot/<job>.json`). After a
  server stop, the plan resumes at the first unfinished step via `start(job_id=…)`. Transient
  failures (voice engine, render, disk) are replayed once — no click, no LLM cost.
- **Bounded auto-correction**: an audit probes the DOM and measurements on a few frames; if defects
  are **measured**, 0 to 2 LLM calls correct and re-render. Never an infinite loop.
- **Clean cancellation**: voice synthesis and rendering honor the job's `cancel_event`; no temporary
  file is left behind.
- **Honest auditing**: the text LLM does not see images. It never claims to have checked contrast
  over media backgrounds, full motion or aesthetics. Visual success still needs a human to confirm.

---

## The AI assistant: it proposes, you apply

The assistant is not a generic chatbot: it **knows the studio by reading its code** (composition
registry, v2 schema, catalog of 25 effects, fonts, `web/package.json`). It does not recite
documentation and never invents an absent `@remotion/*` package or an off-catalog effect.

**Three providers, no automatic fallback**: local LLM (OpenAI-compatible), Gemini, Groq. Settings are
separate; keys never leave the server.

### The proposal contract

The assistant produces a **typed proposal** (`project_new`, `project_patch`, `library_save`,
`batch_plan`, `autopilot_plan`, `question`, `unavailable`), validated server-side by the existing
business logic, then **accepted with a click**. Until you click:

- the candidate lives in memory only, never in the autosave;
- the `resolved` block supplied by the model is **always stripped**;
- a media is accepted only as `media://<uuid>` — any disk path is rejected.

### 32 tools, a clear boundary

| Family | Role | Execution |
| --- | --- | --- |
| **22 read tools** | project, templates, fonts, media, CSV, plan, batches, effects, montage pipelines, EDL validation… | free, bounded |
| **6 proposal tools** | produce a validated `Proposal` | no side effects |
| **4 execution tools** | apply, save, export, start a batch | **only on a user click** |

`tools.describe()` publishes the list **and the prohibitions**: no shell, no `eval`/`exec`, no
model-chosen disk path, no dependency installation, no deletion, no render or batch without a click.
CSVs and documents are treated as **data** (anti-injection clause in the prompt).

### Transparency

Every response carries a `meta`: prompt mode, estimated input tokens, context budget, attempts,
observed models and latencies. LLM responses are not logged; a contract error is returned verbatim to
the model for repair, then to the user in plain language — never hidden behind an approximate answer.

---

## Footage editing: EDL → FFmpeg

The studio is not limited to motion design: it also assembles **real footage** (rushes, transitions,
music, grading). The engine split is deliberate:

- **Remotion** renders the v2 animated compositions (motion design, titles, captions);
- **FFmpeg** assembles real footage through an **EDL** (edit decision list) contract.

The EDL contract and the three-pass assembly engine are a **home-grown implementation**: the
OpenMontage grammar served only as documentation reference, none of its executables are used.
The bridge, wired end to end:

```
the assistant produces edit_decisions (EDL)
    │  cuts of already-ingested media://, transitions, music, grading
    ▼
validate_montage          ← read tool: indexed errors + EDL contract, no writing
    ▼
montage_render {edl,name} ← confirmed action: frozen normalized EDL, no-overwrite,
    │                        media snapshot (size + mtime) → any drift refuses execution
    ▼
POST /api/montage         ← cancellable job, three-pass FFmpeg render
    ▼
MP4 + probe (real vs planned duration, audio, size) + "Open the edit"
```

The EDL contract is **closed**: roles, transitions and grades outside the lists are rejected; errors
are indexed (`cuts[2].out`) so the model can fix them without guessing. Bounds: up to 80 cuts, cuts
from 0.4 to 120 s, total from 2 to 3600 s, transitions ≤ 40% of the shortest cut. The three-pass
FFmpeg render (normalize → assemble → finish) is deliberately robust: heterogeneous codecs,
resolutions and fps, silent rushes, files shorter than expected.

> A plan without a render stays a plan: the assistant never presents an `edit_decisions` as a video.

---

## The 4 laws of the studio

They are **verifiable in the code**, not just written here:

1. **The plan you see is exactly what gets rendered.** `POST /api/batch/plan` and
   `POST /api/batch/start` call the same `build_plan()`. The queue reinvents nothing.
2. **A single render entry point.** `render_project_to_mp4()` is called by the single export **and**
   by the batch worker. No second queue, no second engine.
3. **Nothing is ever filled in silently.** A missing media **blocks** the row; an over-long text is
   **flagged**, never cut; an absent license is written `inconnue`, never validated; the assistant
   triggers no render, no deletion, no batch without a click.
4. **No Windows path crosses the project or the browser.** Media are referenced as `media://<uuid>`
   and served under `/media-cache/<id><ext>`. A brand pack refuses paths and URLs; the delivery ZIP
   name is resolved by the server, never proposed by the client.

---

## Tech stack

| Layer | Technologies | Role |
| --- | --- | --- |
| **Frontend** | React 18 · TypeScript 5.6 · Vite 6 · Tailwind 3 · Remotion 4.0.539 · Radix UI | editing, preview (`@remotion/player`), dialogue, display. Zero business logic. |
| **Backend** | Python 3.12 · FastAPI 0.136 · uvicorn · Pydantic 2 · httpx | 16 routers, origin middleware, path bounding, jobs, subprocesses. |
| **Business engine** | `shortvideos/` (pure, no FastAPI or React) | v2 schema, deterministic resolution, validation, batches, effects, EDL, captions, voice, probe. |
| **Rendering** | Remotion CLI (motion design) · FFmpeg via `imageio-ffmpeg` (footage) | one entry point per engine, portable Node v22. |
| **Assistant** | `server/agent/` · raw httpx · SQLite FTS5 | LLM client, capabilities, retrieval, contract, 32 tools. No execution. |
| **Persistence** | JSON + 2 SQLite databases (production queue, knowledge index) | hand-written SQL, no ORM. |
| **Voice / ASR** | Piper + Kokoro (local TTS) · Whisper Groq or local (detected, never installed) | offline synthesis, on-demand transcription. |

**Deliberately absent**: LangChain, LlamaIndex, OpenAI SDK, SQLAlchemy, CORS (same origin), ffprobe
(OpenCV + `ffmpeg -i`), CDN/remote fonts, Docker, accounts/auth, automatic dependency installation,
a second render engine.

---

## Quick start

### Prerequisites

- **Python 3.12** on the `PATH`.
- **Portable Node v22** expected at `../_tools/node` (the launcher puts it first on the `PATH`;
  nothing is assumed to be installed globally).
- Windows (local single-user machine).

### Run

```bat
start_web.bat
```

The single launcher does, in order: moves to the root · prepares portable Node · checks Python ·
builds the frontend if `web/dist` is missing (`npm install` once, then `tsc --noEmit && vite build`) ·
starts uvicorn on `127.0.0.1:8000` · waits for `/api/health` to respond before opening the browser.
`Ctrl+C` stops the app.

### Useful commands

| Goal | Command |
| --- | --- |
| Run the app | `start_web.bat` |
| Rebuild the frontend | `cd web && npm run build` |
| Hot-reload development | `cd web && npm run dev` (proxy `/api` → `:8000`) |
| Types only | `cd web && npx tsc --noEmit` |
| Server without build | `python -m server.app` (`--open` to open the browser) |
| Tests | `python -m pytest tests -q` → **467 passed** |
| Health | `curl http://127.0.0.1:8000/api/health` |
| Render outside the UI | `python tests/e2e_export_remotion.py` |

### Enable the assistant (optional)

The studio works without an LLM. To enable the assistant, the **Cockpit** shows a guided three-step
setup (provider, URL/key, model) until it is ready. A real test (`POST /api/agent/check`) measures
latency and observed capabilities — never a result inferred from the model name. Keys stay in
`server/settings.json`, never returned over HTTP.

---

## Architecture

```
Browser (http://127.0.0.1:8000)
  React 18 + TypeScript + Vite + Tailwind  ──>  web/dist served by FastAPI (same origin)
       │  Remotion Player 4.0.539 (preview = render)
       │  typed HTTP contract: web/src/api/client.ts
       ▼
FastAPI + uvicorn — 127.0.0.1:8000 — Python 3.12
  server/app.py + 16 routers + origin middleware + path bounding
       │
       ├── shortvideos/   pure business engine: schema, resolution, validation, batches,
       │                  effects, EDL, timeline, captions, voice, b-roll, probe
       ├── server/agent/  assistant: LLM client, capabilities, FTS5 retrieval, contract, tools
       ├── server/queue   persistent SQLite queue + worker + manifest
       ├── server/delivery  batch ZIP package (job, atomic .part.zip)
       ├── server/brands    client brand packs
       ├── server/moments   transcription, scoring, on-demand generation
       └── subprocesses: Remotion render (motion design) · FFmpeg (footage EDL)
                                    ▲
                        Portable Node v22 · local FFmpeg (imageio-ffmpeg)
                        Local Whisper detected, never installed
```

**Who does what**: `web/` edits and displays (zero business logic) · `shortvideos/` carries the pure
business logic (testable on its own) · `server/` transports, secures, persists and launches
subprocesses · `server/agent/` knows the studio and proposes (no execution) · Remotion is the source
of truth for the animated image.

---

## Security

| Control | Verified behavior |
| --- | --- |
| **Listening** | `127.0.0.1` by default, nothing published to the Internet. |
| **Origin** | `POST`/`PUT`/`DELETE`/`PATCH` from a foreign origin ⇒ **403** (including a remote origin claiming to be local). |
| **Paths** | 11 allowed roots; outside these roots ⇒ **400**; no Windows path in URLs, media = `/api/media/<uuid>`. |
| **Traversal** | `../`, encoded paths, invalid identifiers ⇒ **400/404**. |
| **Upload** | image/video MIME types only (otherwise **415**), 500 MB max, empty file rejected. |
| **API keys** | stay server-side; `GET /api/settings` returns only booleans; nothing in logs. |
| **LLM** | no shell, no `eval`/`exec`, no model-chosen disk path, no writing, no deletion, no launch without a click. |
| **CSV / documents** | treated as data, anti-injection clause in the prompt. |
| **`resolved`** | a block supplied by the LLM is always stripped. |
| **Overwrite** | an existing MP4 or project is not replaced without an explicit rule (**409** then confirmation). |
| **Sensitive action** | confirmation token (`hmac.compare_digest`) + freshness re-check (media, EDL) before execution. |

---

## Tests & verification

```bat
python -m pytest tests -q        →  467 passed
```

The tests cover the business logic **and** the guardrails: catalog of 25 effects (uniqueness, bounds,
catalog ↔ render consistency), validation, timing, batch plan, SQLite queue, delivery (cues aligned
to `resolve()`, complete ZIP), brand packs, end-to-end assistant with a mocked LLM (nothing written
before acceptance, invented effect rejected, conflict then rebase), route security, EDL contract and
montage render.

**Real measurements obtained on this machine** (executed, not inferred):

- single export 1080×1920 / 30 fps / 405 frames / 13.5 s, completed;
- real render with effects: 540×960 / 30 fps / 228 frames / 7.6 s, **each of the 25 effects** present,
  no composition failure;
- a 3-row batch rendered end to end from `/production`, CSV and JSON manifests downloaded;
- frontend built with no TypeScript error, pages tested in the browser with **0 console errors**;
- knowledge index: ~290 documents / ~2,300 sections, FTS5 active.

> The assistant's contract is guaranteed by tests, not by a click capture: enabling an LLM would
> require modifying the user's `settings.json`, which the studio does not do without a click.

---

## Project structure

```
youtube_clipper/
├── start_web.bat            single launcher (build + server + browser)
├── ARCHITECTURE.md          full documentation (18 chapters)
├── requirements.txt         Python dependencies
├── server/                  FastAPI backend
│   ├── app.py               application + 16 routers
│   ├── api/                 the routers (montage, batch, delivery, agent…)
│   ├── agent/               assistant: autopilot, tools, proposals, retrieval…
│   ├── render.py            Remotion render entry point
│   ├── queue.py             SQLite queue + worker
│   ├── delivery.py          batch ZIP package
│   ├── imagegen.py          image generation (Pollinations, no key)
│   └── security.py          origins, bounded paths, allowed roots
├── shortvideos/             pure business engine
│   ├── schema.py            v2 project format
│   ├── resolve.py           deterministic resolved block
│   ├── effects.py           catalog of 25 effects
│   ├── edl.py               footage editing EDL contract
│   ├── timeline.py          three-pass FFmpeg render
│   ├── captions.py          caption alignment to the voice
│   ├── broll.py             automatic B-roll, no LLM
│   ├── tts.py               local voice-over (Piper + Kokoro)
│   └── delivery.py          captions, thumbnails, social formats
├── web/                     React + Remotion frontend
│   ├── src/remotion/        compositions (source of truth for the image)
│   ├── src/components/      pages, assistant, UI kit
│   └── public/fonts/        5 SIL OFL families
├── skills/                  knowledge packs (Remotion; montage kept local)
├── tests/                   467 tests
└── brands/ models/ projects/ media/ exports/ batch/   (data, out of repo)
```

---

## Known limitations

The studio is honest about what it does not do:

- **Single-machine, single-user**: no accounts, no shared queue; one active batch at a time.
- **2,000 CSV rows maximum**; vertical 9:16 output in practice (other frames untested).
- **No real 3D, no free vector morphing, no external LUT, no WebGL**: the 25 effects are rendered with
  what is already installed (CSS 3D on planes, SVG filters, 2D canvas). The 3 audio-reactive effects
  only move if real audio is present.
- **The assistant does not see the image**: it reasons over JSON, capabilities and documents, never
  over rendered frames. The technical audit does not guarantee aesthetics.
- **Delivered captions are not a voice transcription**: they reuse the text of the layers actually
  displayed. No ASR in the delivery pipeline (no automatic installation).
- **No automatic audio editing** (beat-matching, dynamic ducking): looping, trimming, fades.
- **Local Whisper detected, never installed**; no automatic local ↔ cloud fallback.
- `server/settings.json` is in clear text on the local disk (single-user machine); it never goes out
  over HTTP.

The exhaustive list and extension recipes are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## License

The code of `shorts-studio` — the architecture, the v2 format, the effects, the assistant, the
autopilot, the EDL/FFmpeg engine and the whole delivery pipeline — is an **original work** under the
**Apache 2.0** license — see [`LICENSE`](LICENSE).

**Third-party libraries.** Remotion is used as a render engine under **its own license** (Remotion
editor); it is neither modified nor redistributed as part of the project. FFmpeg, Piper, Kokoro and
the other dependencies remain under their respective licenses.

**Note on the montage pack.** The production grammar imported from OpenMontage (`skills/montage/`,
**AGPL-3.0** license) is only a **documentation reference read locally**: it is **excluded from the
public repository** (gitignored) and no executable code from OpenMontage is copied into the studio —
only manifests and sheets are read, read-only, by the assistant. The editing engine itself is entirely
rewritten (see above). Tests stay green without this pack. Its provenance (source, commit, license) is
recorded in `skills/montage/PROVENANCE.md` (local).

The shipped fonts are under **SIL OFL** license; TTS voices carry their respective licenses (Piper
GPL-3.0 for the code, Kokoro MIT / model Apache-2.0), recorded in the catalog.

---

## Full documentation

This README is the showcase. The exhaustive reference — every file, every field of the v2 format,
every page panel by panel, every route, every guardrail and its test, the limitations and the
extension recipes — lives in a single document:

**[`ARCHITECTURE.md`](ARCHITECTURE.md)** — 18 chapters, the project's only reference documentation.

<div align="center">

---

*Built to stay local, deterministic and honest: the studio proposes, you decide.*

</div>