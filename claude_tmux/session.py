import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .registry import registry_load, registry_save, registry_add
from .tmux import tmux, tmux_has_session, tmux_active_sessions

SESSION_PREFIX = "claude"


# ── git / group detection ─────────────────────────────────────────────────────

def detect_group(cwd: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        return os.path.basename(result.stdout.strip())
    return os.path.basename(cwd)


def shorten_path(path: str) -> str:
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


# ── claude command ────────────────────────────────────────────────────────────

def build_claude_cmd(resume: str | None = None) -> str:
    parts = ["claude", "--dangerously-skip-permissions"]
    if resume:
        parts += ["--resume", resume]
    return " ".join(parts)


def build_tmux_cmd(claude_cmd: str, session: str) -> str:
    """
    Envuelve claude en un loop de reinicio:
    - Al salir (Ctrl+C, /exit, etc.) pregunta si reiniciar
    - Si sí, lee el resume_id actualizado del registry (post-compactación)
    - Ejecuta _sync-id en cada salida para trazar cambios de ID
    """
    script  = shlex.quote(os.path.abspath(sys.argv[0]))
    sess_q  = shlex.quote(session)
    shell   = os.environ.get("SHELL", "zsh")
    loop = (
        f'trap "" INT; '                                           # bash ignora Ctrl+C, solo Claude lo recibe
        f'_CCMD={shlex.quote(claude_cmd)}; '
        f'while true; do '
        f'  _TS=$(date +%s%3N); '
        f'  eval "$_CCMD"; '
        f'  _EC=$?; '
        f'  {script} _sync-id {sess_q} $_TS; '
        f'  [ "$_EC" -eq 0 ] && break; '
        f'  printf "\\n\\033[33m[claude-tmux] reiniciando...\\033[0m\\n"; '
        f'  sleep 0.5; '
        f'  _RID=$({script} _get-resume-id {sess_q}); '
        f'  _CCMD="claude --dangerously-skip-permissions${{_RID:+ --resume $_RID}}"; '
        f'done; '
        f'exec {shell}'
    )
    return f"bash -c {shlex.quote(loop)}"


def cmd_get_resume_id(session: str) -> None:
    """Imprime el resume_id actual del registry (usado por build_tmux_cmd)."""
    data = registry_load()
    info = data["sessions"].get(session)
    if info and info.get("resume_id"):
        print(info["resume_id"], end="")


def cmd_sync_id(session: str, start_ts: int) -> None:
    """Detecta si Claude cambió de sessionId (compactación) y actualiza el registry."""
    data = registry_load()
    info = data["sessions"].get(session)
    if not info:
        return

    project = info.get("path", "")
    old_id  = info.get("resume_id")

    history_path = Path.home() / ".claude" / "history.jsonl"
    if not history_path.exists():
        return

    latest_id = None
    latest_ts = start_ts

    with history_path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if (entry.get("project") == project
                    and entry.get("timestamp", 0) > latest_ts):
                latest_ts = entry["timestamp"]
                latest_id = entry.get("sessionId")

    if latest_id and latest_id != old_id:
        chain = info.get("id_chain", [])
        if old_id and old_id not in chain:
            chain.append(old_id)
        info["resume_id"] = latest_id
        info["id_chain"]  = chain
        registry_save(data)
        old_short = old_id[:8] if old_id else "—"
        print(f"[claude-tmux] session ID actualizado: {old_short} → {latest_id[:8]}")


def build_session_rows() -> tuple[list[tuple], list[str]]:
    """
    Fuente de verdad: registry.
    rows = (session_name, is_selectable, is_attached, is_running)
    """
    data = registry_load()
    saved = data.get("sessions", {})
    if not saved:
        return [], []

    # Estado actual de tmux
    active_map = {s["name"]: s for s in tmux_active_sessions()}

    groups: dict[str, list] = {}
    ungrouped = []

    for session, meta in saved.items():
        tmux_info  = active_map.get(session)
        is_running = tmux_info is not None
        is_attached = tmux_info["attached"] if tmux_info else False
        entry = (session, meta, is_running, is_attached)
        grp = meta.get("group")
        if grp:
            groups.setdefault(grp, []).append(entry)
        else:
            ungrouped.append(entry)

    rows  = []
    lines = []

    def add_session(session, meta, is_running, is_attached):
        short = session.removeprefix(SESSION_PREFIX + "-")
        if is_attached:
            icon = "▶"   # activa y conectada
        elif is_running:
            icon = "●"   # corriendo en background
        else:
            icon = "○"   # solo en registry, no en tmux
        lines.append(f"    {icon} {short}")
        rows.append((session, True, is_attached, is_running))

    for group, entries in sorted(groups.items()):
        sample_path = shorten_path(os.path.dirname(entries[0][1].get("path", "")))
        lines.append(f"  ◆ {group}  {sample_path}")
        rows.append((None, False, False, False))
        for entry in sorted(entries, key=lambda x: x[0]):
            add_session(*entry)
        lines.append("")
        rows.append((None, False, False, False))

    if ungrouped:
        lines.append("  ◆ (sin grupo)")
        rows.append((None, False, False, False))
        for entry in sorted(ungrouped, key=lambda x: x[0]):
            add_session(*entry)

    return rows, lines


def build_archived_rows() -> tuple[list[tuple], list[str]]:
    data     = registry_load()
    archived = data.get("archived", {})
    rows: list = []
    lines: list = []
    if not archived:
        return rows, lines
    groups: dict[str, list] = {}
    ungrouped = []
    for session, meta in archived.items():
        grp = meta.get("group")
        if grp:
            groups.setdefault(grp, []).append((session, meta))
        else:
            ungrouped.append((session, meta))
    for group, entries in sorted(groups.items()):
        sample_path = shorten_path(os.path.dirname(entries[0][1].get("path", "")))
        lines.append(f"  ◆ {group}  {sample_path}")
        rows.append((None, False, False, False))
        for session, meta in sorted(entries):
            short = session.removeprefix(SESSION_PREFIX + "-")
            lines.append(f"    ▣ {short}")
            rows.append((session, True, False, False))
        lines.append("")
        rows.append((None, False, False, False))
    if ungrouped:
        lines.append("  ◆ (sin grupo)")
        rows.append((None, False, False, False))
        for session, meta in sorted(ungrouped):
            short = session.removeprefix(SESSION_PREFIX + "-")
            lines.append(f"    ▣ {short}")
            rows.append((session, True, False, False))
    return rows, lines


def dashboard_rename_session(old_session: str, new_name: str) -> bool:
    new_name = new_name.strip().replace(" ", "-")
    if not new_name:
        return False
    data = registry_load()
    if old_session not in data["sessions"]:
        return False
    new_session = f"{SESSION_PREFIX}-{new_name}"
    if new_session in data["sessions"]:
        return False
    info = data["sessions"].pop(old_session)
    data["sessions"][new_session] = info
    registry_save(data)
    if tmux_has_session(old_session):
        tmux("rename-session", "-t", old_session, new_session)
        tmux("rename-window", "-t", f"{new_session}:0", new_name)
    return True


def dashboard_archive_session(session: str) -> None:
    data = registry_load()
    if session in data["sessions"]:
        data["archived"][session] = data["sessions"].pop(session)
        registry_save(data)


def dashboard_unarchive_session(session: str) -> None:
    data = registry_load()
    if session in data["archived"]:
        data["sessions"][session] = data["archived"].pop(session)
        registry_save(data)


def dashboard_delete_session(session: str, from_archived: bool = False) -> None:
    data = registry_load()
    if from_archived:
        data["archived"].pop(session, None)
    else:
        data["sessions"].pop(session, None)
        if tmux_has_session(session):
            tmux("kill-session", "-t", session)
    registry_save(data)


def dashboard_open_session(session: str) -> None:
    reg = registry_load()
    if tmux_has_session(session):
        os.execlp("tmux", "tmux", "attach", "-t", session)
    else:
        info      = reg["sessions"].get(session, {})
        name      = session.removeprefix(SESSION_PREFIX + "-")
        cwd       = info.get("path", os.getcwd())
        resume_id = info.get("resume_id")
        cmd       = build_claude_cmd(resume_id)
        tmux("new-session", "-s", session, "-c", cwd, "-n", name, "-d",
             build_tmux_cmd(cmd, session))
        os.execlp("tmux", "tmux", "attach", "-t", session)


def cmd_start(name: str | None, group: str | None, resume: str | None, path: str | None = None) -> None:
    cwd = os.getcwd()

    if not name:
        name = os.path.basename(cwd)

    session = f"{SESSION_PREFIX}-{name}"

    # Si hay --resume o --path, buscar el path en el registry primero
    data = registry_load()
    registered = data["sessions"].get(session)

    if path:
        cwd = os.path.expanduser(path)
    elif resume and registered:
        cwd = registered["path"]
        print(f"Usando path del registry: {shorten_path(cwd)}")

    if not group:
        group = registered["group"] if registered else detect_group(cwd)

    claude_cmd = build_claude_cmd(resume)

    if tmux_has_session(session):
        print(f"Reconectando a {session}  [{group}]")
        os.execlp("tmux", "tmux", "attach", "-t", session)
        return

    print(f"Creando sesión : {session}")
    print(f"Grupo          : {group}")
    print(f"Path           : {shorten_path(cwd)}")
    print(f"Comando claude : {claude_cmd}")

    tmux("new-session", "-s", session, "-c", cwd, "-n", name, "-d",
         build_tmux_cmd(claude_cmd, session))
    registry_add(session, group, cwd, resume_id=resume)
    os.execlp("tmux", "tmux", "attach", "-t", session)


def cmd_chat(resume: str | None) -> None:
    result = tmux("display-message", "-p", "#S")
    session = result.stdout.strip()
    if not session:
        print("Error: no estás dentro de una sesión tmux.", file=sys.stderr)
        sys.exit(1)

    data = registry_load()
    registered = data["sessions"].get(session)
    cwd = registered["path"] if registered else os.getcwd()

    claude_cmd = build_claude_cmd(resume)
    tmux("new-window", "-t", session, "-c", cwd, "-n", "chat",
         build_tmux_cmd(claude_cmd, session))


def cmd_attach(name: str) -> None:
    session = f"{SESSION_PREFIX}-{name}"
    if not tmux_has_session(session):
        print(f"Sesión '{session}' no existe.", file=sys.stderr)
        sys.exit(1)
    os.execlp("tmux", "tmux", "attach", "-t", session)


def cmd_save(name: str, conv_id: str, path: str | None, group: str | None) -> None:
    cwd = os.path.expanduser(path) if path else os.getcwd()
    grp = group or detect_group(cwd)
    data = registry_load()
    data["conversations"][name] = {
        "id": conv_id,
        "group": grp,
        "path": cwd,
        "saved": datetime.now().isoformat(timespec="seconds"),
    }
    registry_save(data)
    print(f"✓ Conversación guardada: {name}")
    print(f"  ID    : {conv_id}")
    print(f"  Grupo : {grp}")
    print(f"  Path  : {shorten_path(cwd)}")


def cmd_resume(name: str) -> None:
    data = registry_load()
    conv = data["conversations"].get(name)
    if not conv:
        available = list(data["conversations"].keys())
        print(f"Conversación '{name}' no encontrada.", file=sys.stderr)
        if available:
            print("Disponibles:", ", ".join(available), file=sys.stderr)
        sys.exit(1)
    print(f"Retomando '{name}'  [{conv['group']}]")
    cmd_start(name, conv["group"], conv["id"], conv["path"])


def cmd_convs() -> None:
    data = registry_load()
    convs = data.get("conversations", {})
    if not convs:
        print("No hay conversaciones guardadas.")
        return
    groups: dict[str, list] = {}
    for name, c in convs.items():
        groups.setdefault(c["group"], []).append((name, c))
    for grp, items in sorted(groups.items()):
        print(f"\n  ◆ {grp}")
        for name, c in sorted(items):
            short_id = c["id"][:8]
            print(f"    ○ {name:<25} {short_id}  {shorten_path(c['path'])}")
    print()


def cmd_restore(attach_first: bool = False) -> None:
    """Recrea sesiones tmux desde el registry tras un reinicio."""
    data     = registry_load()
    sessions = data.get("sessions", {})
    if not sessions:
        print("No hay sesiones en el registry para restaurar.")
        return

    restored = []
    skipped  = []

    for session, info in sessions.items():
        if tmux_has_session(session):
            skipped.append(session)
            continue

        cwd       = info.get("path", os.getcwd())
        resume_id = info.get("resume_id")
        name      = session.removeprefix(SESSION_PREFIX + "-")
        cmd       = build_claude_cmd(resume_id)

        if not os.path.isdir(cwd):
            print(f"  ⚠  {session}  —  path no existe: {cwd}")
            continue

        tmux("new-session", "-s", session, "-c", cwd, "-n", name, "-d",
             build_tmux_cmd(cmd, session))
        restored.append(session)
        print(f"  ✓  {session:<35} {shorten_path(cwd)}")

    if not restored and not skipped:
        print("Nada que restaurar.")
        return

    if restored:
        print(f"\n{len(restored)} sesión(es) restaurada(s).")
    if skipped:
        print(f"{len(skipped)} ya estaban activas: {', '.join(s.removeprefix(SESSION_PREFIX + '-') for s in skipped)}")

    if attach_first and restored:
        os.execlp("tmux", "tmux", "attach", "-t", restored[0])


def cmd_kill(name: str) -> None:
    """Mata la sesión tmux pero la conserva en el registry."""
    session = f"{SESSION_PREFIX}-{name}"
    if tmux_has_session(session):
        tmux("kill-session", "-t", session)
        print(f"✓ Sesión '{session}' terminada (conservada en registry).")
    else:
        print(f"  Sesión '{session}' no estaba corriendo.")
    data = registry_load()
    if session not in data["sessions"]:
        print(f"  '{session}' tampoco está en el registry.", file=sys.stderr)


def cmd_restart(name: str, no_attach: bool = False) -> None:
    """Mata la sesión tmux atascada y la recrea desde el registry."""
    session = f"{SESSION_PREFIX}-{name}"
    data    = registry_load()
    info    = data["sessions"].get(session)

    if not info:
        print(f"Sesión '{session}' no encontrada en el registry.", file=sys.stderr)
        print("Usa 'claude-tmux list' para ver las sesiones disponibles.", file=sys.stderr)
        sys.exit(1)

    if tmux_has_session(session):
        tmux("kill-session", "-t", session)
        print(f"  ✗  Sesión anterior terminada.")

    cwd       = info.get("path", os.getcwd())
    resume_id = info.get("resume_id")
    cmd       = build_claude_cmd(resume_id)

    if not os.path.isdir(cwd):
        print(f"  ⚠  El directorio ya no existe: {cwd}", file=sys.stderr)
        sys.exit(1)

    print(f"  ↺  Recreando '{session}'  [{info.get('group', '?')}]")
    print(f"     Path   : {shorten_path(cwd)}")
    if resume_id:
        print(f"     Resume : {resume_id[:8]}…")

    tmux("new-session", "-s", session, "-c", cwd, "-n", name, "-d",
         build_tmux_cmd(cmd, session))
    print(f"  ✓  Sesión recreada.")

    if not no_attach:
        os.execlp("tmux", "tmux", "attach", "-t", session)


def cmd_upgrade() -> None:
    """Descarga la última versión del script desde GitHub y lo reemplaza."""
    url    = "https://raw.githubusercontent.com/davidsuarezcdo/claude-tmux/main/claude-tmux"
    target = Path(os.path.abspath(sys.argv[0]))

    if not os.access(target, os.W_OK):
        print(f"  ✗  Sin permiso de escritura en {target}", file=sys.stderr)
        print(f"     Intenta: sudo claude-tmux upgrade", file=sys.stderr)
        sys.exit(1)

    curl = shutil.which("curl") or shutil.which("wget")
    if not curl:
        print("  ✗  Se requiere curl o wget para hacer upgrade.", file=sys.stderr)
        sys.exit(1)

    tmp = target.with_suffix(".tmp")
    try:
        if os.path.basename(curl) == "curl":
            result = subprocess.run(
                ["curl", "-fsSL", url, "-o", str(tmp)],
                capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["wget", "-qO", str(tmp), url],
                capture_output=True, text=True,
            )

        if result.returncode != 0:
            print(f"  ✗  Error al descargar: {result.stderr.strip()}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            sys.exit(1)

        # Verificar que el archivo descargado es el script correcto
        content = tmp.read_text(encoding="utf-8", errors="ignore")
        if "claude-tmux" not in content or "SESSION_PREFIX" not in content:
            print("  ✗  El archivo descargado no parece válido.", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            sys.exit(1)

        tmp.chmod(0o755)
        tmp.replace(target)
        print(f"  ✓  claude-tmux actualizado en {target}")

    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"  ✗  Error inesperado: {e}", file=sys.stderr)
        sys.exit(1)


def _pick_with_fzf(rows: list, lines: list) -> str | None:
    """Selección con fzf. Devuelve session_name o None."""
    selectable = [(r, l) for r, l in zip(rows, lines) if r[1]]
    fzf_input = "\n".join(l.strip() for _, l in selectable)
    result = subprocess.run(
        ["fzf", "--ansi", "--prompt=sesión> ", "--height=40%", "--reverse"],
        input=fzf_input, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    chosen = result.stdout.strip()
    for (name, _), (_, line) in zip(selectable, [(r, l) for r, l in zip(rows, lines) if r[1]]):
        if line.strip() == chosen:
            return name
    return None
