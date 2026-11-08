## 2026-10-22 - Subprocess Environment Variable Leakage
**Vulnerability:** The application was passing the entire environment (`os.environ`) containing sensitive cloud API keys to a child `bash` subprocess in `TerminalManager`.
**Learning:** By default, `subprocess.Popen` inherits the entire environment from the parent process. If this subprocess is exposed (e.g., to an LLM running skills), it can exfiltrate sensitive secrets.
**Prevention:** Scrub the environment dictionary explicitly (e.g. `env.pop(key, None)`) for known secrets before passing it into a `subprocess`.
## 2024-05-18 - Subprocess Environment Variable Leakage (Build/MCP)
**Vulnerability:** The application was passing the entire environment (`os.environ`) containing sensitive cloud API keys to child subprocesses in `BuildManager` and MCP `McpManager`.
**Learning:** By default, `subprocess.run` and MCP server connections inherit the entire environment from the parent process, exposing secrets to third-party tools or scripts.
**Prevention:** Scrub the environment dictionary explicitly (e.g., `env.pop(key, None)`) using the centralized `_PROVIDER_ENV` for known secrets before passing it into external process environments.
## 2024-05-24 - Credentials leakage through unscrubbed subprocesses
**Vulnerability:** API keys and sensitive environment variables can leak into sub-processes launched using `subprocess.run` or `subprocess.Popen` without explicitly providing an explicitly scrubbed `env` parameter. I found these vulnerabilities when calling `subprocess.Popen` to start ComfyUI (which runs untrusted custom nodes) and the updater script in `justllama/server/updater.py`.
**Learning:** System environment is inherited automatically when creating a new subprocess, meaning API keys meant only for this application could be accessed by untrusted third-party code like external models or install scripts.
**Prevention:** Always scrub sensitive information from `os.environ.copy()` before passing it explicitly via the `env=` keyword argument to any subprocess spawning functions. Use `_PROVIDER_ENV` dictionary in `justllama.config.env` to safely strip any configured keys.
## 2024-05-25 - Additional Subprocess Environment Variable Leakage
**Vulnerability:** Several `subprocess.run` and `os.execvp` calls were missing environment scrubbing. This included `git` commands and `npx` execution in `gemma_skills_mcp.py`, `nvidia-smi` in `models/profiles.py` and `models/browser.py`, and `fuser` in `server/manager.py`.
**Learning:** It is easy to miss environment scrubbing for seemingly benign utility commands (`git`, `nvidia-smi`, `fuser`), but passing unscrubbed environments is dangerous if those utilities or their wrapping scripts are ever compromised or exploit environment variables in unexpected ways. Furthermore, `os.execvp` inherits the environment natively; `os.execvpe` must be used to provide a scrubbed environment.
**Prevention:** Always use `env=env` with a scrubbed environment for `subprocess.run`/`subprocess.Popen` calls, and use `os.execvpe` instead of `os.execvp` when replacing the process.
## 2024-05-26 - Path Traversal in BuildManager
**Vulnerability:** The `BuildManager` class allowed arbitrary file read, write, edit, and listing (path traversal) outside its designated `_work_dir` because it failed to resolve and validate file paths provided via JSON `BUILD_OP` commands.
**Learning:** When creating filesystem tools for LLM agents, paths must be explicitly bound. Simple string concatenation or `Path()` wrapping is not enough if relative paths like `../` or absolute paths are provided by an untrusted source.
**Prevention:** Use a safe path resolution helper that employs `Path.resolve()` combined with `Path.is_relative_to(safe_dir)` to guarantee operations cannot escape the sandbox. Reject absolute paths or resolve them safely against the sandbox root.
## 2024-05-27 - Command Injection in shell script generation
**Vulnerability:** External input from GitHub API (`tag_name`) was interpolated directly into double quotes in a dynamically generated Bash script without `shlex.quote` in `justllama/server/updater.py`.
**Learning:** Even if data comes from a trusted external API like GitHub, dynamically building Bash scripts with Python string interpolation is inherently vulnerable to Command Injection if quotes are escaped.
**Prevention:** Always use `shlex.quote()` on any variable dynamically written into a shell script or passed to `shell=True` subprocess calls. Remove surrounding double quotes when doing so.
