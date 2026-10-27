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
