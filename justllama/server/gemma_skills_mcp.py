import os
import sys
import subprocess
from pathlib import Path

def main():
    repo_url = "https://github.com/google-gemma/gemma-skills"
    skills_dir = Path.home() / ".local" / "share" / "justllama" / "gemma-skills"
    
    if not skills_dir.exists():
        skills_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "clone", repo_url, str(skills_dir)], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[Gemma Skills] Failed to clone repo: {e.stderr.decode()}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            subprocess.run(["git", "-C", str(skills_dir), "pull"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[Gemma Skills] Failed to pull repo: {e.stderr.decode()}", file=sys.stderr)
            # Continue anyway, we might be offline

    # Execute the filesystem MCP server exposing the repository directory
    # Using sys.executable to ensure we use the same environment if needed, but npx is external.
    # Replace the current process with npx.
    try:
        os.execvp("npx", ["npx", "-y", "@modelcontextprotocol/server-filesystem", str(skills_dir)])
    except OSError as e:
        print(f"[Gemma Skills] Failed to launch filesystem MCP server: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
