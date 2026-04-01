import json
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path.home() / ".config" / "claude-tmux" / "registry.json"


def registry_load() -> dict:
    if REGISTRY_PATH.exists():
        data = json.loads(REGISTRY_PATH.read_text())
        data.setdefault("conversations", {})
        data.setdefault("archived", {})
        return data
    return {"sessions": {}, "conversations": {}, "archived": {}}


def registry_save(data: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2))


def registry_add(session: str, group: str, path: str, resume_id: str | None = None) -> None:
    data = registry_load()
    entry = {
        "group": group,
        "path": path,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    if resume_id:
        entry["resume_id"] = resume_id
    data["sessions"][session] = entry
    registry_save(data)


def registry_remove(session: str) -> None:
    data = registry_load()
    data["sessions"].pop(session, None)
    registry_save(data)


def registry_prune(active_sessions: set[str]) -> None:
    """Elimina del registry sesiones que ya no existen en tmux."""
    data = registry_load()
    dead = [s for s in data["sessions"] if s not in active_sessions]
    for s in dead:
        data["sessions"].pop(s)
    if dead:
        registry_save(data)
