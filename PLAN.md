# Smart Junction Decision Engine — Project Plan

> Editable hackathon plan; no project code is included. Scope is one simulated four-way junction, with an explainable decision engine and dashboard. Plan assumes 12 focused hours for one developer. Signal instructions are generated for review and are never sent to hardware.

## 1. Project Overview

**Problem:** Estimate traffic demand from multiple sources, adapt signal timing, prioritize trusted emergency requests, and generate structured instructions for compatible controllers.

**Objective:** Build a working four-way prototype that adapts timings while enforcing conflict safety and fairness.

**Demo:** Enter or simulate counts, inspect congestion and recommendations, watch the simulated signal/countdown, explicitly confirm an emergency request, and inspect decision history and generic controller JSON.

## 2. Goals, Scope, Success Criteria

### Goals
- Manual counts, seeded simulation, and video with pretrained YOLO vehicle counting.
- Estimate count and low/medium/high congestion for N, E, S, W.
- Bounded green duration based on demand and wait; fairness maximum wait.
- Never serve conflicting approaches simultaneously; use safe phase transitions.
- Trusted emergency priority; ordinary changes only at phase boundaries.
- Dashboard, durable decision history, and versioned controller instruction JSON.

### Out of scope
- Connecting to real signal hardware, sending instructions, or claiming deployment readiness.
- Training a model or claiming reliable emergency-vehicle recognition from arbitrary footage.
- Turning lanes, pedestrian phases, multi-junction coordination, or production networking.

### Acceptance criteria
- [ ] Manual and simulated observations work independently of YOLO.
- [ ] All four approach counts and congestion categories are shown.
- [ ] Recommendations are bounded and include reasons.
- [ ] Signal moves GREEN → YELLOW → ALL_RED → next GREEN; never multiple greens.
- [ ] Ordinary changes wait for a safe phase boundary.
- [ ] Only operator-confirmed emergency requests are trusted; fairness waits are retained and explainable.
- [ ] Dashboard shows state, countdown, next phase, emergency status, and recommendations.
- [ ] SQLite history persists observations, recommendations, reasons, timestamps, and execution status.
- [ ] Generic versioned JSON is marked simulation-only and not sent.
- [ ] YOLO video path returns counts/confidence for chosen sample footage or reports a clear failure without breaking core paths.

## 3. User, Demo Story, and Assumptions

**User:** hackathon judge/operator. Demo with seeded uneven queues, compare recommendations, explicitly confirm an emergency request, observe safe transition, then inspect history and instruction JSON.

**Approach model:** N/E/S/W are four mutually exclusive phases. Exactly one approach receives green. This conservative model omits turning movements and pedestrians.

**Approved demo defaults:** min green 8 s; max green 45 s; yellow 3 s; all-red 1 s; fairness maximum wait 90 s; planning tick 1 s. These are editable software-demo values, not road-engineering recommendations.

Counts are non-negative integers. Simulator uses a fixed seed. YOLO vehicle counting is planned using pretrained weights and a selected sample clip; detector availability and approach mapping must be confirmed early.

## 4. Architecture and End-to-End Data Flow

React dashboard → FastAPI JSON API → Python domain/services → SQLite. Signal execution is simulated.

1. User submits manual counts, selects seeded simulation, or uploads video.
2. Adapter validates input. YOLO adapter processes video with pretrained weights and returns per-approach detections/confidence; its failure does not affect other sources.
3. Estimator normalizes four approach observations and congestion.
4. Optimizer scores demand and wait, applies constraints/fairness and operator-confirmed emergency rule, and records reasons.
5. Phase controller enforces GREEN → YELLOW → ALL_RED → GREEN; ordinary plan changes queue until a boundary.
6. API transactionally persists observation, recommendation, scores, and simulated execution state.
7. Dashboard polls current state every second; history is fetched on demand.
8. Generic versioned instruction JSON is generated with `mode=simulation_only` and `transmission_status=not_sent`.

## 5. Safety, Fairness, Decision Rules

- Model one active phase at a time. State transitions are centralized and validated.
- Clamp recommended green to configured min/max. Invalid input falls back to safe configured values.
- Ordinary timing changes never interrupt active green; apply only at phase boundary.
- Emergency trust for the demo comes from an explicit operator confirmation in the dashboard. A user-entered vehicle label is never proof. No automatic YOLO emergency recognition is in the initial scope.
- Operator-confirmed requests schedule the requested approach at the next safe boundary, after yellow/all-red clearance. Record reason; keep pending until served, cancelled, or expired.
- Track wait seconds for each approach; an approach reaching 90 seconds is eligible for fairness priority. Emergency service does not reset other approaches’ wait clocks. Explain overrides.
- Stale or missing observations show a stale indicator; after configured freshness window use zero-demand defaults rather than treating invalid data as valid.
- Every decision records reason, algorithm version, and status: planned, applied_simulated, rejected, or failed.
- This is a predictable demo model, not certified traffic control.

## 6. Data Model and SQLite Schema

Use SQLite foreign keys, parameterized queries, ISO-8601 UTC timestamps, whole-second durations, nonnegative counts. Integer primary keys unless specified.

### approaches
- `id INTEGER PRIMARY KEY`
- `code TEXT NOT NULL UNIQUE CHECK(code IN ('N','E','S','W'))`
- `display_name TEXT NOT NULL`
- One approach has many approach observations, emergency requests, and one wait row.

### observations
- `id INTEGER PRIMARY KEY`
- `observed_at TEXT NOT NULL`
- `source TEXT NOT NULL CHECK(source IN ('manual','simulation','video'))`
- `source_ref TEXT NULL` (upload/job or simulator run)
- `status TEXT NOT NULL CHECK(status IN ('accepted','partial','rejected'))`
- `created_at TEXT NOT NULL`
- One observation has four approach_observations.

### approach_observations
- `id INTEGER PRIMARY KEY`
- `observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE`
- `approach_id INTEGER NOT NULL REFERENCES approaches(id)`
- `vehicle_count INTEGER NOT NULL CHECK(vehicle_count >= 0)`
- `congestion TEXT NOT NULL CHECK(congestion IN ('low','medium','high'))`
- `confidence REAL NULL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1))`
- `waiting_seconds INTEGER NOT NULL DEFAULT 0 CHECK(waiting_seconds >= 0)`
- `created_at TEXT NOT NULL`
- `UNIQUE(observation_id, approach_id)`

### signal_phases
- `id INTEGER PRIMARY KEY`
- `phase_code TEXT NOT NULL UNIQUE`
- `approach_id INTEGER NOT NULL UNIQUE REFERENCES approaches(id)`
- `min_green_seconds INTEGER NOT NULL CHECK(min_green_seconds > 0)`
- `max_green_seconds INTEGER NOT NULL CHECK(max_green_seconds >= min_green_seconds)`
- `yellow_seconds INTEGER NOT NULL CHECK(yellow_seconds >= 0)`
- `all_red_seconds INTEGER NOT NULL CHECK(all_red_seconds >= 0)`
- `enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))`

### emergency_requests
- `id INTEGER PRIMARY KEY`
- `approach_id INTEGER NOT NULL REFERENCES approaches(id)`
- `requested_at TEXT NOT NULL`
- `expires_at TEXT NULL`
- `trust_status TEXT NOT NULL CHECK(trust_status IN ('trusted','untrusted','rejected'))`
- `status TEXT NOT NULL CHECK(status IN ('pending','scheduled','served','expired','rejected','cancelled'))`
- `request_ref TEXT NULL UNIQUE`
- `decision_reason TEXT NULL`
- `created_at TEXT NOT NULL`

### decisions
- `id INTEGER PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `observation_id INTEGER NULL REFERENCES observations(id)`
- `emergency_request_id INTEGER NULL REFERENCES emergency_requests(id)`
- `current_phase_code TEXT NULL REFERENCES signal_phases(phase_code)`
- `next_phase_code TEXT NOT NULL REFERENCES signal_phases(phase_code)`
- `recommended_green_seconds INTEGER NOT NULL CHECK(recommended_green_seconds > 0)`
- `reason TEXT NOT NULL`
- `algorithm_version TEXT NOT NULL`
- `execution_status TEXT NOT NULL CHECK(execution_status IN ('planned','applied_simulated','rejected','failed'))`
- `instruction_json TEXT NOT NULL`
- Decision references its input observation/emergency request and has approach score rows.

### decision_approach_scores
- `id INTEGER PRIMARY KEY`
- `decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE`
- `approach_id INTEGER NOT NULL REFERENCES approaches(id)`
- `demand_score REAL NOT NULL`, `wait_score REAL NOT NULL`, `total_score REAL NOT NULL`
- `selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0,1))`
- `UNIQUE(decision_id, approach_id)`

### signal_state
- `id INTEGER PRIMARY KEY CHECK(id = 1)` (singleton)
- `phase_code TEXT NULL REFERENCES signal_phases(phase_code)`
- `state TEXT NOT NULL CHECK(state IN ('GREEN','YELLOW','ALL_RED','IDLE'))`
- `phase_started_at TEXT NULL`, `state_started_at TEXT NOT NULL`
- `remaining_seconds INTEGER NOT NULL CHECK(remaining_seconds >= 0)`
- `next_phase_code TEXT NULL REFERENCES signal_phases(phase_code)`
- `active_decision_id INTEGER NULL REFERENCES decisions(id)`
- `updated_at TEXT NOT NULL`

### approach_waits
- `approach_id INTEGER PRIMARY KEY REFERENCES approaches(id)`
- `waiting_seconds INTEGER NOT NULL DEFAULT 0 CHECK(waiting_seconds >= 0)`
- `last_served_at TEXT NULL`
- `updated_at TEXT NOT NULL`

Indexes: observations(observed_at), decisions(created_at), emergency_requests(status, requested_at). Seed exactly four approaches/phases, singleton state, and four waits. Enable foreign keys on every connection. Persist decision and score rows in one transaction. Instruction JSON is an immutable audit snapshot.

## 7. Backend Modules, Functions, API Contracts

### Modules and functions
- `app/main.py`: FastAPI app, router registration, startup.
- `app/db.py`: schema initialization, connections, transactions.
- `app/schemas.py`: Pydantic contracts and validation.
- `app/config.py`: timing, stale threshold, fairness and model settings.
- `app/inputs/manual.py`: `normalize_manual_counts(payload)`.
- `app/inputs/simulation.py`: `generate_simulated_observation(seed, profile)`.
- `app/inputs/video.py`: `create_video_job(file)`, `process_video_job(job_id)`, pretrained YOLO inference and approach aggregation.
- `app/services/estimator.py`: `estimate_congestion(count)`, `build_observation(...)`.
- `app/services/optimizer.py`: `score_approaches(...)`, `recommend_phase(...)`, `clamp_green(...)`.
- `app/services/phase_controller.py`: `validate_transition(...)`, `advance_state(...)`, `queue_plan(...)`.
- `app/services/instructions.py`: `build_instruction(...)`; never transmits.
- `app/services/history.py`: persistence and queries.
- Routers: `traffic.py`, `signals.py`, `emergencies.py`, `history.py`.

JSON uses ISO UTC timestamps. Invalid inputs return 422; unknown IDs 404; unavailable YOLO returns a clear job failure/503 without disabling other inputs.

| Method / route | Input | Output |
|---|---|---|
| GET `/api/health` | none | `{status,version,database}` |
| POST `/api/observations/manual` | `{counts:{N:int,E:int,S:int,W:int},waiting_seconds?:{N:int,E:int,S:int,W:int}}` | `{observation_id,observed_at,approaches:[{code,vehicle_count,congestion,waiting_seconds}],decision?}` |
| POST `/api/observations/simulate` | `{seed?:int,profile?:"balanced"\|"rush"\|"sparse"}` | observation shape plus seed and decision |
| POST `/api/observations/video` | multipart `file` | `{job_id,status,detail}`; completion includes counts/confidence or unavailable/failure |
| GET `/api/observations/{id}` | path ID | observation and four approach estimates |
| GET `/api/signals/current` | none | `{state,active_phase,remaining_seconds,next_phase,updated_at,emergency_status,recommendation}` |
| POST `/api/signals/tick` | `{elapsed_seconds?:int}` | updated simulated state |
| POST `/api/emergencies` | `{approach:"N"\|"E"\|"S"\|"W",operator_confirmed:true,expires_in_seconds?:int}` | `{request_id,status,scheduled_phase,reason}`; no confirmation is rejected |
| POST `/api/emergencies/{id}/cancel` | none | updated request status |
| GET `/api/history?limit=50&cursor=...` | optional bounded pagination | `{items:[decision + observation summary],next_cursor}` |
| GET `/api/decisions/{id}` | path ID | decision, scores, reason, status, instruction |
| GET `/api/decisions/{id}/instruction` | path ID | versioned JSON with simulation_only/not_sent |

Instruction: `{schema_version:"1.0",decision_id,created_at,junction_id:"demo-junction-1",phase:{code,approach,green_seconds,yellow_seconds,all_red_seconds},valid_until,mode:"simulation_only",transmission_status:"not_sent"}`.

## 8. Frontend Pages, Routes, Interactions

- `/` Dashboard: four approach cards, current signal/countdown, next phase, emergency state, recommendations, stale indicator.
- `/input` Traffic Input: manual and simulation tabs; video upload and YOLO job/count status.
- `/history` Decision History: time, source, selected phase, duration, reason, execution status, filters.
- `/history/:decisionId` Decision Detail: scores, observation, reason, instruction JSON, copy/download.
- `/settings` Demo Settings: editable timing/fairness values and simulator profile; validate min ≤ max.

Shared components: `AppShell`, `ApproachCard`, `SignalCountdown`, `EmergencyStatus`, `RecommendationList`, `InputForm`, `VideoJobStatus`, `OperatorEmergencyConfirm`, `DecisionTable`, `InstructionJson`, `ErrorNotice`.

One API client; visible loading/empty/stale/error states; poll current state every second on dashboard. Backend alone owns authoritative decisions and transitions.

## 9. Folder Tree and File Purposes

```text
smart-junction-decision-engine/
├── PLAN.md                         # Editable plan
├── README.md                       # Setup, demo steps, limitations
├── .gitignore                      # Local DB, uploads, environments, build output
├── .env.example                    # Configuration names and safe defaults
├── backend/
│   ├── requirements.txt            # Python dependencies including YOLO runtime
│   ├── app/
│   │   ├── main.py                 # FastAPI app/startup
│   │   ├── config.py               # Timing, fairness, model configuration
│   │   ├── db.py                   # SQLite schema and transactions
│   │   ├── schemas.py              # Validated API models
│   │   ├── routers/
│   │   │   ├── traffic.py          # Observation endpoints
│   │   │   ├── signals.py          # State/tick endpoints
│   │   │   ├── emergencies.py      # Operator-confirmed priority
│   │   │   └── history.py          # History/decision/instruction endpoints
│   │   ├── inputs/
│   │   │   ├── manual.py           # Manual count normalization
│   │   │   ├── simulation.py       # Seeded traffic source
│   │   │   └── video.py            # Upload and pretrained YOLO adapter
│   │   └── services/
│   │       ├── estimator.py        # Counts to congestion
│   │       ├── optimizer.py        # Scores and recommendation
│   │       ├── phase_controller.py # Safe simulated transitions
│   │       ├── instructions.py     # Generic controller JSON
│   │       └── history.py          # Persistence/query logic
│   ├── data/                       # Ignored local SQLite database
│   └── uploads/                    # Temporary ignored video files
└── frontend/
    ├── package.json                # React dependencies/scripts
    ├── index.html                  # SPA entry
    └── src/
        ├── main.jsx                # React mount
        ├── App.jsx                 # Routes/shell
        ├── api/client.js           # API wrappers/error handling
        ├── pages/
        │   ├── DashboardPage.jsx   # Live simulated status
        │   ├── InputPage.jsx       # Manual, simulation, video
        │   ├── HistoryPage.jsx     # Decision list
        │   ├── DecisionPage.jsx    # Decision detail
        │   └── SettingsPage.jsx    # Demo settings
        ├── components/             # Reusable interface pieces
        └── styles/                 # Global/page styles
```

## 10. Coding Rules and Quality Bar

- Domain rules belong in services; routers validate/call/shape responses.
- Use small functions, type hints, Pydantic validation, consistent errors.
- Keep manual/simulation independent of video imports and model initialization.
- Seed simulation for repeatability; keep all signal changes inside phase controller.
- Clamp durations centrally; reject negative counts, invalid approach/state, malformed timestamps.
- Record reason, algorithm version, provenance, and execution status.
- Every instruction says simulation-only/not sent; no hardware transmission code.
- Keep secrets out of source; document config names in .env.example.
- Handle stale data, backend outage, empty history, invalid forms, unavailable YOLO, and expired requests visibly.
- Use text and color for signal states; record safety/schema/timing changes in decisions log.
- README must enable a fresh local demo.

## 11. Twelve-Hour Solo Build Schedule and Slice Order

| Time | Slice | Done when |
|---|---|---|
| 0:00–0:30 | Setup folders, dependencies, config, README skeleton | Both apps start |
| 0:30–1:30 | SQLite schema, seeds, health route | Repeatable initialization |
| 1:30–2:30 | Manual input and estimator | Four counts return congestion |
| 2:30–3:30 | Seeded simulator | Repeatable without YOLO |
| 3:30–5:00 | Optimizer | Bounds, wait/fairness, reasons and score rows |
| 5:00–6:30 | Phase controller | Safe cycle and boundary-only plan changes |
| 6:30–7:30 | Emergency request | Operator-confirmed request; invalid unconfirmed request rejected |
| 7:30–9:00 | React shell, dashboard, input | State, counts, recommendation, next phase visible |
| 9:00–10:00 | History and decision detail | Records persist; instruction inspectable |
| 10:00–10:45 | Instruction contract | Versioned simulation-only JSON |
| 10:45–11:15 | YOLO video-counting feasibility slice | Chosen clip yields per-approach counts or clear fallback; core paths remain usable |
| 11:15–12:00 | Integration, README, demo rehearsal | Fresh start, complete core checklist |

Dependency order: contracts/schema → manual → simulation → optimizer → safe phase simulation → emergency/fairness → dashboard → history/instruction → YOLO → polish. If YOLO setup exceeds its 30-minute slice, report unavailable and finish the demo via manual/simulation; do not imply video counting succeeded.

## 12. Progress Checklist, Current State, Decisions Log

### Progress checklist
- [x] Plan reviewed
- [x] Frontend/backend start locally
- [x] Schema and seed data initialize
- [x] Manual observations work end-to-end
- [x] Simulation works independently of video
- [x] Congestion appears for all four approaches
- [x] Bounded recommendation, scores, and reason work
- [x] Fairness ceiling is visible and explainable
- [x] Operator-confirmed emergency request is recorded
- [x] Safe transitions prevent conflicting greens
- [x] Ordinary updates apply at boundaries
- [ ] Dashboard shows state/countdown/recommendation/next phase
- [ ] History persists observations and decisions/status
- [ ] Instruction endpoint returns generic simulation-only JSON
- [ ] Pretrained YOLO video counting works on selected sample or reports clear failure
- [ ] README enables a fresh demo and explains limits

### CURRENT STATE
- **Plan status:** Active execution
- **Project code:** Slices 1, 2, 3, 4, 5, 6, and 7 completed
- **Completed slice:** Operator-confirmed emergency priority and safe boundary scheduling (Slice 7)
- **Open risk:** YOLO weights/runtime and reliable mapping to four approaches need early feasibility confirmation. The referenced brief preview was truncated; this plan uses the visible brief content and the user's answers.
- **Next action:** Implement React dashboard UI with live countdown and approach cards (Slice 8)
- **Last updated:** 2026-10-30

### Decisions log

| Date | Decision | Reason / consequence |
|---|---|---|
| 2026-10-29 | Four mutually exclusive NESW phases | User prefers NESW for now; avoids conflicting greens in this prototype |
| 2026-10-29 | SQLite, FastAPI, React | Fast local single-junction demo stack |
| 2026-10-29 | Manual and seeded simulation remain core independent inputs | Keeps prototype usable if video/model fails |
| 2026-10-29 | Use pretrained YOLO for video vehicle counting | User chose YOLO; isolate and time-box dependency |
| 2026-10-29 | Operator confirmation establishes demo emergency trust | Safe understandable default while evaluation requirements are unknown |
| 2026-10-29 | Generic versioned instruction JSON, simulation-only/not sent | User confirmed this is fine; the demo displays a simple example and never sends it to real equipment |
| 2026-10-29 | Retain 8–45 s green, 3 s yellow, 1 s all-red, 90 s fairness defaults | User approved these editable demo values; not field guidance |
| 2026-10-30 | Congestion thresholds: low (<=4), medium (5-12), high (>=13) | Clear, transparent demo queue classification; easily configurable in estimator |
| 2026-10-30 | Isolated PRNG simulation profiles (balanced, rush, sparse) | Deterministic repeatability across demo runs without global random side-effects; reuses core persistence and estimation |
| 2026-10-30 | Demand/wait scoring (weights 1.0/0.5), 90s fairness ceiling, deterministic NESW tie-breaker, and transactional decision persistence | Ensures explainable, bounded signal recommendations with strict audit persistence in SQLite |
| 2026-10-30 | Centralized phase controller state machine (GREEN -> YELLOW -> ALL_RED -> GREEN) | Strictly prevents conflicting greens; queues ordinary decisions until safe clearance boundaries |
| 2026-10-30 | Operator-confirmed emergency scheduling at next safe boundary | Eliminates spoofing by requiring explicit operator confirmation; serves emergency after clearance without resetting other waits |

### Five questions about remaining unclear or risky choices

1. Which sample video or camera view should be used to validate YOLO, and will it show the four approaches from a fixed, known viewpoint?
2. Should emergency priority remain an operator-confirmed demo action, or does the evaluation provide a specific trusted request source?
3. Does the hackathon environment allow using pretrained YOLO weights and the required runtime, or must the demo work fully offline?
4. What video file format and maximum clip length should the upload accept for the YOLO demo?
5. Is the 12-hour build window fixed, and should YOLO receive its scheduled 30-minute feasibility slice even if the rest of the prototype needs more integration time?


