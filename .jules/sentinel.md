## 2026-10-22 - Subprocess Environment Variable Leakage
**Vulnerability:** The application was passing the entire environment (`os.environ`) containing sensitive cloud API keys to a child `bash` subprocess in `TerminalManager`.
**Learning:** By default, `subprocess.Popen` inherits the entire environment from the parent process. If this subprocess is exposed (e.g., to an LLM running skills), it can exfiltrate sensitive secrets.
**Prevention:** Scrub the environment dictionary explicitly (e.g. `env.pop(key, None)`) for known secrets before passing it into a `subprocess`.
