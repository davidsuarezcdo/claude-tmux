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


def tmux_session_panes(session: str) -> list[dict]:
    """Devuelve panes extra de una sesión (índice > 0 = agentes del team).

    Cada dict tiene: index, command, active.
    Solo retorna los panes adicionales al pane principal (index 0).
    """
    result = tmux(
        "list-panes", "-t", session,
        "-F", "#{pane_index}|#{pane_current_command}|#{pane_active}",
    )
    if result.returncode != 0:
        return []
    panes = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            idx = int(parts[0])
            if idx > 0:   # pane 0 = el loop principal de claude-tmux
                panes.append({
                    "index":   idx,
                    "command": parts[1],
                    "active":  parts[2] == "1",
                })
    return panes
