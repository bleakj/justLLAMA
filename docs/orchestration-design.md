# justLLAMA Orchestration — Design Sketch

Draft: 2026-11-26. Status: design only, no code written.
Goal: turn justLLAMA from a single-user chat workbench into Justin's own
harness, running his builder → reviewer loop exactly the way he already
works — no premade orchestrator, no change to the loop to fit a tool.

## The loop this must run

Planner → Critic → Planner revise/redo → Build → Review → Build, looping
until done. Sequential only — never two agents working the same project at
once. One writer per workspace.

Hard rules (from how he already works):
- Builder never reviews its own work. Reviewer is read-only.
- Max 2 failed attempts per item, then stop with a summary + diff + what failed.
- No time limit on runs.
- Completion is judged by exit code + diff + test run, never by the agent
  saying "done".
- Human gate before anything destructive / scope-crossing (merge, deploy,
  irreversible actions). Justin is the final gate.
- Prompts are detailed and guarded; reviewer output is a verdict file
  (PROCEED / DO NOT PROCEED + blockers + should-fixes), not prose.

## Where it lives

The current GUI stays fully usable — orchestration is additive, not a
rewrite. Existing tabs and managers keep working untouched; orchestration
arrives as a new manager (same pattern as CouncilManager) plus a new tab
that starts runs, shows step progress, approves gates, and browses run
history. The GUI is the control surface either way.

New package: `justllama/orchestration/` — headless-safe by construction.
Core modules import no Qt at all. This is the key structural decision:
the existing managers (council, chat, build) are QObject/QThread wired to
QML and cannot run in a plain script. The orchestrator does not reuse them
by import; it reuses their *patterns* and the Qt-free helpers underneath
them. Decision (2026-11-26, Justin): execution lives in the GUI. If the
application closes, the run stops. No out-of-process mode, no resume
across restarts. Consequences:
- The runner is a QThread worker (CouncilRunner pattern) inside the GUI
  app; the QML tab is the control surface (start/stop/progress/gates) and
  is part of Phase 1, not Phase 2.
- Shutdown must stop the runner and kill its child CLI processes — no
  orphaned agents. This is the stop behavior that council/chat currently
  get wrong (BUG-5, BUG-9); the orchestrator's stop must actually work.
- Run checkpoints + JSONL log remain as the audit trail, not as resume
  machinery.
- Prerequisite: the `muse` and `codex` CLIs must be installed on the
  machine that runs the justLLAMA GUI.

## Modules (Phase 1)

```
justllama/orchestration/
├── __init__.py
├── adapters/
│   ├── __init__.py        # adapter registry: name -> adapter
│   ├── base.py            # AgentAdapter: run(prompt, workdir, timeout) -> RunResult
│   ├── muse_cli.py        # `muse exec` (Spark) — --json JSONL, --prompt-file
│   ├── codex_cli.py       # `codex exec` (Sol/Terra, Plus login) — --json JSONL
│   ├── antigravity.py     # `agy` headless (Neon) — JSON event on stdin, --model, --sandbox
│   └── llama_server.py    # local models via existing LlamaClient (HTTP)
├── state.py               # RunState: plan, critique, diff summary, verdict,
│                          # attempt counters, step history. JSON checkpoint
│                          # written after every step; JSONL run log on disk.
├── pipeline.py            # the state machine: step registry + routing function.
│                          # Routing (not prompts) owns looping and termination:
│                          # max-2 attempts, verdict parsing, stop conditions.
├── verifier.py            # evidence, not prose: run pytest, capture exit code,
│                          # git diff --stat, test counts. Verdict = pass/fail
│                          # from these, never from agent output text.
├── gates.py               # human gates: pause run, persist state, resume on
│                          # explicit approval (CLI flag / approval file).
├── runner.py              # drives steps: timeouts, per-step budgets, stop
│                          # conditions, progress events. Runs on a worker
│                          # thread; never blocks the UI thread.
└── manager.py             # QObject wrapper: QML slots (start/stop/approve)
                           # and signals (progress/step/gate). Owns the
                           # runner thread; stops it + kills child processes
                           # on app shutdown. No standalone CLI entry.
```

Entry: the QML orchestration tab. The manager exposes start (project +
task file), stop, and approve/deny gate slots; progress arrives via
signals. No standalone CLI entry.

## Roles → models (defaults, configurable per run)

| Role | Default agent | Why |
|------|--------------|-----|
| Planner | Neon via `agy` (verify on his machine first) — fallback: local Inkling 2 Mini via llama-server | planning-only, different model family from reviewer |
| Critic | Sol via `codex exec` (read-only) | independent second set of eyes on the plan |
| Builder | Spark via `muse exec` | builds only, never reviews |
| Reviewer | Sol via `codex exec` (read-only) | same reviewer family as critic, separate from builder |

Rules enforced in code, not convention: builder adapter and reviewer
adapter must differ; the critic node is a separate step from the planner
node (a planner revising its own plan after an independent critique is
fine — it is not a builder reviewing its own code).

## What gets reused from existing justLLAMA

- **Council pattern** (`server/council.py`): sequential dispatch, progress
  signals, failure placeholders, restore-main-model. Copy the shape, not
  the Qt code. Council itself is hard-wired to 3 models / one prompt each.
- **Build ops** (`server/build.py`): path-traversal guard + work-dir
  scoping. Reuse the guard logic; the orchestrator's verifier replaces the
  string-with-exit-code result with structured evidence.
- **Providers** (`server/providers.py`): cloud API definitions for any
  API-key step. The loop itself uses subscription CLIs, not API keys.
- **Memory** (`memory/`): run history can live in the same SQLite store
  later; Phase 1 uses plain JSON/JSONL files per run (simpler, inspectable).
- **Settings**: headless runs should not depend on QSettings. Phase 1 reads
  a small run config file (TOML/JSON) for model assignments + paths.

## Known traps (from ANALYSIS.md — fix or route around)

- BUG-5: council stop unresponsive (`wait()` on UI thread). BUG-9: chat
  stop freezes UI. BUG-12: build `run` blocks UI up to 60s. If any
  orchestration step reuses council/chat/build code paths, these threading
  bugs become orchestration bugs. The headless package avoids them by not
  importing the Qt managers.
- No CLI-agent transport exists today: no subprocess runner for coding
  CLIs, no JSONL parsing, no turn budgets. This is the biggest new piece.
- `codex exec` has no `--max-turns` flag — the runner must enforce attempt
  and turn budgets itself.
- Full automation needs approval-bypass flags (`muse --yolo`, codex
  `--dangerously-bypass-approvals-and-sandbox`). Trust decision: reviewer
  stays read-only, builder sandboxed to the project workdir, never bypass
  on a machine with anything precious.
- Plus has per-5-hour message limits (Codex); Muse Code High has its own
  pool. An unsupervised loop can eat both fast — the runner tracks usage
  per run and stops on a budget.

## Phases

**Phase 1 — minimal working loop (est. 2–4 focused days).**
Adapters for `muse exec` + `codex exec`; state + pipeline for the single
loop above; verifier (pytest + git diff); JSON checkpoint + JSONL run log
(audit trail); human gate as pause/resume via QML buttons; runner as
QThread worker + manager exposed to QML; minimal QML orchestration tab
(start/stop/status/gates/run log). No separate CLI entry, no worktrees, no
resume across restarts. Success = the justDECKS-style loop runs end to end
on a test project without a human in the middle except at the gate.

**Phase 2 — isolation + visibility (est. 1 week more).**
Git worktree per run (builder works isolated, merge only at the gate);
richer QML tab (run history browser backed by the JSONL logs).

**Phase 3 — full harness (as needed).**
Neon via `agy` adapter (verify headless `agy` on his machine first —
Augani's adapter documents JSON-on-stdin + `--model` + `--sandbox`, but
it is unverified here); local-model roles via llama-server; per-run
usage/cost tracking; resume-from-checkpoint in the UI.

## Explicitly not building

- Parallel agents on the same project (his rule — sequential only).
- Auto-merge or auto-deploy (gates stay human).
- API-key model access for the loop (subscriptions via CLIs instead).
- A second model-access layer inside the GUI — the GUI keeps doing chat;
  the orchestrator is a separate entry point that happens to live in the
  same repo.

## Open verifications (before Phase 1 code)

1. `agy` headless on his machine (Antigravity installed? `agy --help`?
   JSON stdin protocol as Augani documents it?).
2. `muse exec` JSONL event schema on his installed version (verified
   conceptually 2026-11-26: `--json`, `--prompt-file`, `--model
   muse-spark-1.3-contributor`).
3. `codex exec` on his installed version (verified conceptually
   2026-11-26: `--json`, `--model`, default `gpt-6.1-sol`, Plus login via
   `~/.codex/auth.json`).
