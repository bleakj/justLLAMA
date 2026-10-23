## 2026-10-22 - Subprocess Environment Variable Leakage
**Vulnerability:** The application was passing the entire environment (`os.environ`) containing sensitive cloud API keys to a child `bash` subprocess in `TerminalManager`.
**Learning:** By default, `subprocess.Popen` inherits the entire environment from the parent process. If this subprocess is exposed (e.g., to an LLM running skills), it can exfiltrate sensitive secrets.
**Prevention:** Scrub the environment dictionary explicitly (e.g. `env.pop(key, None)`) for known secrets before passing it into a `subprocess`.
## 2024-05-18 - Subprocess Environment Variable Leakage (Build/MCP)
**Vulnerability:** The application was passing the entire environment (`os.environ`) containing sensitive cloud API keys to child subprocesses in `BuildManager` and MCP `McpManager`.
**Learning:** By default, `subprocess.run` and MCP server connections inherit the entire environment from the parent process, exposing secrets to third-party tools or scripts.
**Prevention:** Scrub the environment dictionary explicitly (e.g., `env.pop(key, None)`) using the centralized `_PROVIDER_ENV` for known secrets before passing it into external process environments.
