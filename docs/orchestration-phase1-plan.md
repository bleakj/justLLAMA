Build Phase 1 of orchestration inside the justLLAMA GUI app, in the project folder. justLLAMA is a PySide6/Kirigami desktop workbench for llama.cpp. Execution lives inside the GUI: if the app closes, the run stops. Do not build a separate CLI entry or daemon.

Goal: run this loop end to end from a new orchestration tab — Planner → Critic → Planner revise → Build → Review → Build, sequential, one writer per project, looping until done.

Build these items, in this order:

1. New package `justllama/orchestration/` with a Qt-free core (no PySide imports in the core modules; Qt only in `manager.py` and QML). Modules: `adapters/base.py`, `adapters/muse_cli.py`, `adapters/codex_cli.py`, `state.py`, `pipeline.py`, `verifier.py`, `gates.py`, `runner.py`, `manager.py`.
2. `adapters/base.py`: an adapter interface with one method — run a prompt in a project directory and return a structured result (exit code, stdout text, list of changed files, error string). Every adapter takes the model and workdir as parameters; never hardcode a model name.
3. `adapters/muse_cli.py`: run the `muse` CLI headless with `--json` and a prompt file; parse its line-delimited JSON output; surface the final text and exit code through the base result.
4. `adapters/codex_cli.py`: run the `codex` CLI headless with `--json` and a `--model` parameter; parse its line-delimited JSON output the same way. Note: this CLI has no max-turns flag, so the runner (item 9) enforces attempt budgets.
5. `state.py`: a run-state record (plan text, critique text, diff summary, verdict, attempt counters, step history). Write a JSON checkpoint after every step and append each step to a JSONL run log in the project folder. These are the audit trail; there is no resume across restarts.
6. `pipeline.py`: the step registry and routing function for Planner → Critic → Planner revise → Build → Review → Build. The routing function — not the prompts — owns looping and termination: max 2 attempts per item, then stop with a summary and diff. Parse verdicts from a verdict file with a first line of PROCEED or DO NOT PROCEED, followed by blockers and should-fixes. Enforce in code that the builder adapter and the reviewer adapter are different instances.
7. `verifier.py`: evidence, not prose. Run the project's test command, capture exit code and pass/fail counts, and capture `git diff --stat`. A step passes only when the tests pass and the diff is non-empty where a change was expected. Never judge completion from the agent's output text.
8. `gates.py`: pause the run before any destructive or scope-crossing step; resume only on explicit approval from the UI.
9. `runner.py`: drive the steps on a worker thread. Never block the UI thread. Check a stop flag between steps and before/after blocking calls. Stop must terminate the child CLI processes — see ANALYSIS.md BUG-5 and BUG-9 for the failure mode to avoid. Follow the sequential-dispatch shape in `server/council.py`; reuse the path guard in `server/build.py`.
10. `manager.py`: a QObject wrapper exposing start (project + task file), stop, and approve/deny slots, plus progress/step/gate signals. Register it as a QML context property in `main.py` following the existing managers. Wire app shutdown to stop the runner and kill child processes.
11. Minimal QML orchestration tab following the existing tab patterns: project + task file pickers, start/stop buttons, step progress and status text, gate approve/deny buttons, and a run-log view.
12. Tests: pytest coverage for the Qt-free core — adapters against fake CLI scripts, pipeline routing and termination, verdict parsing, verifier against a fixture repo, gates. Keep the full existing suite green.

Constraints: do not change existing managers or tabs except the wiring in `main.py` and the new tab. Do not add a standalone CLI entry, worktrees, or resume-across-restart. If a build step fails twice, stop that item and report what failed with the diff. No time limit on the run.

Finish with: a summary of files changed, the full test-suite result (pass/fail counts), and how to start a run from the new tab.
