import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from .registry import registry_load
from .tmux import tmux_active_sessions
from .session import SESSION_PREFIX, shorten_path


def load_history() -> list[dict]:
    path = Path.home() / ".claude" / "history.jsonl"
    if not path.exists():
        return []
    sessions: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = entry.get("sessionId")
            if not sid:
                continue
            ts      = entry.get("timestamp", 0)
            display = entry.get("display", "").strip()
            project = entry.get("project", "")
            if sid not in sessions:
                sessions[sid] = {
                    "sessionId": sid,
                    "project":   project,
                    "first_ts":  ts,
                    "last_ts":   ts,
                    "first_msg": display,
                    "last_msg":  display,
                    "count":     1,
                }
            else:
                s = sessions[sid]
                if ts < s["first_ts"]:
                    s["first_ts"]  = ts
                    s["first_msg"] = display
                if ts > s["last_ts"]:
                    s["last_ts"]  = ts
                    s["last_msg"] = display
                    s["project"]  = project
                s["count"] += 1
    return sorted(sessions.values(), key=lambda x: x["last_ts"], reverse=True)


def get_active_conv_ids() -> set[str]:
    """Retorna sessionIds que tienen sesión tmux activa."""
    active = {s["name"] for s in tmux_active_sessions()}
    data   = registry_load()
    result = set()
    for name, info in data["sessions"].items():
        if name in active and info.get("resume_id"):
            result.add(info["resume_id"])
    return result


def fmt_ts(ts_ms: int) -> str:
    dt  = datetime.fromtimestamp(ts_ms / 1000)
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("hoy %H:%M")
    elif (now - dt).days < 7:
        dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
        return f"{dias[dt.weekday()]} {dt.strftime('%H:%M')}"
    return dt.strftime("%d/%m/%y")


def _pick_history_fzf(items: list[dict], active_ids: set[str]) -> dict | None:
    lines = []
    for item in items:
        sid     = item["sessionId"]
        project = os.path.basename(item["project"]) if item["project"] else "?"
        msg     = item["first_msg"][:55].replace("\n", " ")
        date    = fmt_ts(item["last_ts"])
        icon    = "🟢" if sid in active_ids else "  "
        lines.append(f"{icon} {project:<20} {date:<12} {msg}")

    result = subprocess.run(
        ["fzf", "--ansi", "--prompt=historial> ", "--height=60%", "--reverse"],
        input="\n".join(lines), capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    chosen = result.stdout.strip()
    for item, line in zip(items, lines):
        if line == chosen:
            return item
    return None


def cmd_history() -> None:
    from .dashboard import run_dashboard, MODE_HISTORY
    run_dashboard(MODE_HISTORY)
