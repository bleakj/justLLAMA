# justllama — Full Analysis & Bug Report

> **Status update (2026-07-28):** Phase 0 is done — the stale
> `test_settings.py` expectation was fixed and the suite is green:
> **447 passed** (verified with `QT_QPA_PLATFORM=offscreen
> python3 -m pytest tests/ -q`).
>
> **The 3 CRITICAL bugs below are now FIXED** and guarded by regression
> tests in `tests/test_known_bugs.py` (previously strict-xfail, now plain
> passing assertions):
> - **BUG-1** — `VectorStore.clear()` now deletes the collection *before*
>   re-creating it, so the bound handle stays live.
> - **BUG-2** — `_restore_server` (imagegen + videogen) parses
>   `server/n_gpu_layers` via `get_string` + try/except (council.py idiom),
>   so the shipped `"auto"` default no longer raises and the server is
>   restored after generation.
> - **BUG-3** — the ComfyUI health probe now targets `/system_stats` (an
>   endpoint ComfyUI serves), and a failed health check aborts with cleanup
>   (`stop_comfyui` + `_restore_server` + early `return`) before
>   `_post_prompt` runs.
>
> BUG-8 (.env path) was fixed in the prior commit. The HIGH/MEDIUM/LOW
> items below remain open for follow-up per the Fix Loop Plan.

## Summary
- **Project**: PySide6/Kirigami desktop GUI wrapping llama.cpp llama-server
- **Codebase**: ~15k LOC (45 Python modules, 18 QML files)
- **Static analysis**: All files compile cleanly
- **Test suite**: 439 passed, **1 failed** (stale test)
- **Hardware**: No Xvfb available for headless UI test; Qt imports OK

---

## Bugs Found (17 total)

### CRITICAL (3)

#### BUG-1: VectorStore.clear() destroys collection then holds stale reference [vectorstore.py:241-254]
**Severity**: Critical (breaks RAG after clear)
**File**: `justllama/rag/vectorstore.py` lines 241-254
**Bug**: `clear()` calls `get_or_create_collection(name)` (returns existing), then `delete_collection(name)` (removes from ChromaDB). `self._collection` now references a **deleted** collection object. Any subsequent `add_documents()` or `query()` call raises a ChromaDB NotFoundError. `count()` catches the exception silently → returns 0, masking the problem until add_documents fails.
**Fix**: Delete collection first, then call `get_or_create_collection` to create a fresh one:
```python
def clear(self):
    self._ensure_client()
    try:
        self._client.delete_collection(self._collection_name)
    except Exception:
        pass
    self._collection = self._client.get_or_create_collection(
        name=self._collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    ...
```

#### BUG-2: `get_int("server/n_gpu_layers")` crashes when value is "auto" [imagegen.py:127, videogen.py:149]
**Severity**: Critical (server never restores after image/video gen)
**Files**: `imagegen.py:127` (`ctx = settings.get_int("server/ctx_size")`, `gpu = settings.get_int("server/n_gpu_layers")`), `videogen.py:149` identical
**Bug**: Default `server/n_gpu_layers` is the string `"auto"` in settings.py line 30. `get_int()` calls `int(self._s.value(key, 0))` → `int("auto")` raises **ValueError**. The `_restore_server()` helper catches exceptions broadly and emits a generic error, but the server is never restored — llama-server stays dead after image/video generation.
**Fix**: Use the same pattern as `council.py` lines 54-58:
```python
n_gpu_raw = settings.get_string("server/n_gpu_layers")
try:
    gpu = int(n_gpu_raw)
except (ValueError, TypeError):
    gpu = n_gpu_raw if n_gpu_raw else "auto"
```
Same pattern for `ctx_size` (less likely to crash since default is int 0).

#### BUG-3: ComfyUI health check polls non-existent `/health` endpoint (always times out, 60s waste per gen) [comfy_helpers.py:31, imagegen.py:100, videogen.py:122]
**Severity**: Critical (every generation wastes 60 seconds + emits spurious error)
**Files**: 
- `comfy_helpers.py` line 18: `HEALTH_URL = f"http://[IP_ADDRESS]:{PORT}/health"`
- `imagegen.py` line 100: `wait_for_comfy_health(comfy_proc, _LAUNCH_TIMEOUT)` — polls forever
- `videogen.py` line 122: same
**Bug**: ComfyUI does NOT expose a `/health` endpoint (confirmed by grepping ComfyUI's server.py). The endpoint list includes `/`, `/prompt`, `/history`, `/queue`, `/system_stats`... but no `/health`. `wait_for_comfy_health` loops 60 times with 1s sleep = always times out. Additionally:
  - imagegen line 100-102: missing `return` after emitting the error — code **continues** to `_post_prompt()` against a dead/non-ready ComfyUI server.
  - videogen lines 122-126: same missing early return, plus `stop_comfyui` called then falls through to `_post_prompt` against killed process.
**Fix**: 
1. Replace `HEALTH_URL` polling with `/system_stats` (which ComfyUI does expose).
2. Add `return` after health-check failure in both `_execute()` methods (with proper cleanup: `stop_comfyui` + `_restore_server`).

### HIGH (6)

#### BUG-4: Updater compares release tag to commit hash — always shows "update available" [updater.py:181]
**Severity**: High (false update prompt every time)
**File**: `updater.py` line 181
**Bug**: `_current_version` is set to commit hash `"c0bc8591e"`. `_on_check_result` compares `tag != self._current_version`. Release tags (e.g. "b1009") never equal a commit hash → always emits `update_available`. Also, the install script writes `llama-server` to `/usr/local/bin/` but the app is configured to use `~/.local/bin/llama-server-cuda` — update has no effect on the binary the app launches.
**Fix**: Store release tag name (not commit hash) as `_CURRENT_VERSION`. Fix install script to write to `~/.local/bin/llama-server-cuda` or update the default binary path to match.

#### BUG-5: Council stop unresponsive (UI freeze up to 120s when stopping mid-query) [council.py:247-249, 119-199]
**Severity**: High (UI hangs when user clicks Stop)
**File**: `council.py`
**Bug**: `CouncilManager.stop()` calls `self._runner.wait()` on the **UI thread**. `CouncilRunner._execute()` blocks in `client.chat_completion(stream=False, timeout=120)` and `_wait_for_health()` (30 sleep loops). Neither checks `self._stop_requested`. Stop is effectively unresponsive during model queries and health waits.
**Fix**: 
1. Do NOT call `wait()` on the UI thread. Set `_stop_requested = True` and let the runner check it in its loops.
2. Add `_stop_requested` checks in `_wait_for_health()` (between sleep iterations) and periodically in `_execute()` (before/after blocking calls).
3. For `chat_completion` (blocking HTTP), abort by closing the connection — use `urllib.request` with a short timeout + check flag, or use a `requests` session that supports immediate close from another thread.

#### BUG-6: Stale health worker can kill a newly-started server [manager.py:55-66, 216-226]
**Severity**: High (narrow race window can kill freshly-started llama-server)
**File**: `manager.py` lines 216-226 (`_on_health_failure`)
**Bug**: When the old council model's process dies, `_HealthWorker` emits `failure` → `_on_health_failure` kills `self._process`. If a new server was started in the 1-2 second window between old process death and health worker check, `self._process` points to the **new** process → gets killed by SIGKILL.
**Fix**: Track which health worker emitted the signal; only act if it's still `self._health_worker`:
```python
def _on_health_failure(self, msg: str):
    worker = self.sender()  # or capture worker id at emit time
    if worker is not self._health_worker:
        return
    ...
```

#### BUG-7: `ComfyAgentSkill.timeout = 360.0` is module-level, not class attr — SkillsManager never sees it [comfy_agent.py:29]
**Severity**: High (6-min budget never honored; 30s default used)
**File**: `comfy_agent.py` line 29
**Bug**: `timeout = 360.0` sits at module scope. `SkillsManager.execute_tool` does `getattr(skill, "timeout", timeout)` on the **instance** — never finds it, falls back to default 30s. A 6-minute generation gets killed at 30s every time.
**Fix**: Change to `class ComfyAgentSkill(AgentSkill): timeout = 360.0` (class attribute).

### MEDIUM (5)

#### BUG-8: `env.py` `.env` path points to package dir, not project root [env.py:9]
**Severity**: Medium (README misleads users)
**File**: `config/env.py` line 9
**Bug**: `_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"` resolves to `<repo>/justllama/.env` (inside the Python package). README says to copy `.env.example` to project root `.env`, which won't be read. For pip-installed packages, writing to `justllama/.env` inside site-packages is problematic.
**Fix**: Either update `_ENV_PATH` to use project root (e.g., `Path.cwd() / ".env"` or env var), or update README to instruct placing `.env` inside the package dir.

#### BUG-9: `ChatRunner.stop_generation()` blocks UI thread via `wait()` [chat_manager.py:475]
**Severity**: Medium (UI freezes on Stop until current HTTP round-trip completes)
**File**: `chat_manager.py` line 475 (`self._runner.wait()`)
**Bug**: `stop_generation()` is called from QML (UI thread) and calls `self._runner.wait()` which blocks the UI thread until `ChatRunner.run()` returns. `run()` may be blocked in `iter_lines()` on an HTTP stream — up to 120s if the server is slow or the model is generating a long response.
**Fix**: Don't `wait()` on UI thread. Instead call `stop()` (which closes the response) and let the runner finish asynchronously; the QML UI already disables the Send button based on `isGenerating` property; the `generation_complete`/`error_occurred` signals fire when done.

#### BUG-10: `wait_for_generation` returns stale results after failed `generate_from_workflow` [imagegen.py:359-369, videogen.py:427-437]
**Severity**: Medium (wrong result reported to LLM after partial failure)
**File**: `imagegen.py:367-369`, `videogen.py:434-437`
**Bug**: `wait_for_generation` returns `(self._last_output, self._last_error)`. If `generate_from_workflow` exited early (invalid JSON, no model selected, etc.) without creating a new runner AND a previous run succeeded, `_last_output`/`_last_error` hold stale values from the old run. The skill then reports those stale results to the LLM as if the new generation succeeded.
**Fix**: Reset `_last_output` and `_last_error` to `None` when `generate_from_workflow` is called (since any failure to start a new run should not return stale data), or track the runner instance and only return results from the matching runner.

#### BUG-11: Queued lambda for `_last_output`/`_last_error` causes race in `wait_for_generation` [imagegen.py lines 297-299]
**Severity**: Medium (skill/tool calls can return (None, None) on success)
**File**: `imagegen.py:297-299`, `videogen.py:357-359, 422-424`
**Bug**: `_last_output`/`_last_error` are set via queued lambda connections (default Qt queued → UI thread). `wait_for_generation` is called from a skill executor thread AFTER `self._runner.wait()` returns, but the queued lambdas setting `_last_output`/`_last_error` haven't executed yet in the UI event loop → skill reads `None, None` even though generation succeeded.
**Fix**: Set `_last_output`/`_last_error` directly in the `ImageGenRunner.run()` method (in the worker thread) — e.g., emit signals that pass the filepath/error directly, or capture the result in a thread-safe way (e.g., a `QMutex`-protected property). Alternatively connect with `Qt.DirectConnection`.

#### BUG-12: `build.py apply_operation` — `run_command` blocks UI thread up to 60s [build.py:58-73]
**Severity**: Medium (UI freezes for up to 60s for `run` operations)
**File**: `build.py` line 62 (`timeout=60` in `subprocess.run`)
**Bug**: `apply_operation` is a QML-invoked Slot that runs on the UI thread. For `op_type="run"`, it calls `subprocess.run(..., timeout=60)`. If a command runs for 60s, the UI freezes for a full minute with no cancel option.
**Fix**: Move `run_command` to a QThread worker (as BuildManager already is a QObject — just make `run_command` async).

### LOW (3)

#### BUG-13: Dead setting `server/fit` in QSettings [settings.py:38]
**Severity**: Low (no UI or code path reads it for server launch)
**File**: `config/settings.py` line 38 (default `"server/fit": False`)
**Bug**: `get_all_server_config()` does NOT include `fit`, `numa`, or other keys. Server launched via `get_effective_config()` also doesn't include them. Setting `server/fit` in the UI has no effect. Server always starts with `--fit off` per `config.py:109`. (By design: "we manage VRAM ourselves".)
**Fix**: Either remove from defaults (cleaner) or expose in Settings UI and wire into `get_all_server_config()`.

#### BUG-14: Unused `seen` set in `ModelBrowser.scan()` [browser.py:93]
**Severity**: Low (dead code)
**File**: `models/browser.py` line 93-106
**Bug**: `seen = set()` created on line 93 but never used. Dead variable.
**Fix**: Remove.

#### BUG-15: `TerminalManager` singleton created before `QGuiApplication` exists [terminal_manager.py:166]
**Severity**: Low (minor)
**File**: `terminal_manager.py` line 166
**Bug**: Module-level `terminal_manager = TerminalManager()` runs at import time, before `main.py` calls `QGuiApplication(sys.argv)`. QObject creation before a QApplication instance is unusual; may cause subtle issues on some platforms (Qt internal state not fully initialized).
**Fix**: Defer singleton creation to `main.py` (lazy), or move to a function-level initialization.

### INFO (2)

#### INFO-16: `_all_subclasses` in skills/manager.py is dead code [manager.py:292-302]
**Fix**: Remove unused function.

#### INFO-17: `server/fit` included in `get_all_server_config()` is missing from `get_effective_config()` — gap between QSettings schema and profile merging [settings.py, profiles.py]
**Fix**: Either add `fit` to `get_effective_config()` eff dict or remove from `get_all_server_config()`.

---

## Fix Loop Plan

### Phase 0: Fix test (quick win, 1 test fix)
1. Update `tests/test_settings.py::TestGetAllServerConfig.test_returns_dict_with_all_keys` to include `mmproj` and `spec_type` in `expected_keys`.

### Phase 1: Critical fixes (blocks normal operation)
1. Fix `VectorStore.clear()` BUG-1 — delete-before-recreate pattern.  
2. Fix `n_gpu_layers="auto"` crash in `_restore_server` BUG-2 — use get_string+int try/except pattern.  
3. Fix ComfyUI `/health` endpoint BUG-3 — switch to `/system_stats`, and add early return + proper cleanup path in imagegen and videogen `_execute()`.  
4. Fix updater version comparison BUG-4 — store tag name, compare semver, fix install path.

### Phase 2: Threading & responsiveness fixes (UX blockers)
5. Fix council stop responsiveness BUG-5 — remove `wait()` from UI thread, add `_stop_requested` checks in loops.  
6. Fix stale health worker race BUG-6 — identity-check sender in `_on_health_failure`.  
7. Fix `stop_generation()` UI freeze BUG-9 — remove `wait()` from UI thread.  
8. Fix `wait_for_generation` race BUG-11 — set `_last_output` from worker thread.

### Phase 3: Robustness fixes
9. Fix ComfyAgentSkill timeout BUG-7 — class attribute.  
10. Fix `wait_for_generation` stale results BUG-10 — runner identity tracking.  
11. Fix `env.py` `.env` path BUG-8 — align with README/project root.  
12. Fix `build.py apply_operation` UI freeze BUG-12 — async worker.

### Phase 4: Code hygiene
13. Remove dead `seen` set (BUG-14).  
14. Remove dead `_all_subclasses` (INFO-16).  
15. Move `TerminalManager` singleton init to `main.py` (BUG-15).  
16. Align `server/fit` across settings/get_all_server_config/get_effective_config (INFO-17).

---

## UI Improvement Plan (if user prefers post-bug)

Once bugs are fixed, consider these UI improvements:
1. **Image/Video gen inline preview** — show a thumbnail in ChatView when generation completes (currently requires navigating to Images tab).
2. **Streaming server logs in a collapsible panel** — expose llama-server log output in UI for debugging GPU/VRAM issues.
3. **Council mode progress per model** — show a progress bar per council slot during multi-model query (currently only text "Querying Model 2/3...").
4. **Memory browser with delete confirmation** — Memory view lacks bulk delete and confirmation dialogs.
5. **Dark/light theme toggle in system tray** — quick toggle without opening Settings.
