import subprocess


def tmux(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def tmux_has_session(session: str) -> bool:
    return tmux("has-session", "-t", session).returncode == 0


def tmux_active_sessions() -> list[dict]:
    """Devuelve lista de dicts con name, attached, windows."""
    result = tmux("ls", "-F", "#{session_name}|#{session_attached}|#{session_windows}")
    if result.returncode != 0:
        return []
    sessions = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            sessions.append({
                "name": parts[0],
                "attached": parts[1] == "1",
                "windows": int(parts[2]),
            })
    return sessions
