import curses
import os

from .registry import registry_load
from .tmux import tmux_has_session
from .session import (
    SESSION_PREFIX,
    build_session_rows, build_archived_rows,
    dashboard_rename_session, dashboard_archive_session,
    dashboard_unarchive_session, dashboard_delete_session,
    dashboard_open_session, build_claude_cmd, build_tmux_cmd,
    detect_group, cmd_restart, cmd_start,
)
from .history import load_history, get_active_conv_ids, fmt_ts

MODE_SESSIONS = "sessions"
MODE_HISTORY  = "history"
MODE_ARCHIVED = "archived"

PAD        = 2   # left padding (horizontal)
HEADER_TOP = 2   # blank rows before the header bar (vertical top margin)
LOGO = (
    "▄▖▜      ▌    ▗        ",
    "▌ ▐ ▀▌▌▌▛▌█▌  ▜▘▛▛▌▌▌▚▘",
    "▙▖▐▖█▌▙▌▙▌▙▖  ▐▖▌▌▌▙▌▞▖",
)


def run_dashboard(start_mode: str = MODE_SESSIONS) -> None:
    pending = [None]  # ("open_session", session) | ("open_history", item)

    def _ui(stdscr):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(1, curses.COLOR_CYAN,    -1)
        curses.init_pair(2, curses.COLOR_GREEN,   -1)
        curses.init_pair(3, curses.COLOR_WHITE,   -1)
        curses.init_pair(4, curses.COLOR_YELLOW,  -1)
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)
        curses.init_pair(6, 8,                    -1)
        curses.init_pair(7, curses.COLOR_RED,     -1)
        curses.init_pair(8, curses.COLOR_BLUE,    -1)
        C_HDR    = curses.color_pair(1) | curses.A_BOLD
        C_RUN    = curses.color_pair(2) | curses.A_BOLD   # verde bold → carpetas/grupos
        C_ACTIVE = curses.color_pair(3)                   # sin color → sesiones corriendo
        C_NORM   = curses.color_pair(3)
        C_CUR    = curses.color_pair(4) | curses.A_BOLD
        C_HELP   = curses.color_pair(5)
        C_DIM    = curses.color_pair(6)
        C_ARCH   = curses.color_pair(7)
        C_TAB    = curses.color_pair(8)
        C_SRCH   = curses.color_pair(5) | curses.A_BOLD

        mode   = start_mode
        cursor = 0
        scroll = 0
        query  = ""

        rename_on     = False
        rename_buf    = ""
        rename_target = None
        del_target    = None
        del_arch      = False
        restart_target = None
        name_prompt   = False   # pedir nombre de sesión al abrir historial
        name_buf      = ""
        name_item     = None    # history item pendiente de abrir
        new_sess_prompt = False
        new_sess_buf    = ""

        def load_data():
            if mode == MODE_SESSIONS:
                return build_session_rows()
            elif mode == MODE_ARCHIVED:
                return build_archived_rows()
            else:
                return load_history(), get_active_conv_ids()

        rows, extra = load_data()

        def refresh():
            nonlocal rows, extra, cursor, scroll
            rows, extra = load_data()
            cursor = 0
            scroll = 0

        def put(y, x, s, attr=curses.A_NORMAL):
            h, w = stdscr.getmaxyx()
            if 0 <= y < h and 0 <= x < w:
                try:
                    stdscr.addstr(y, x, str(s)[:w - x - 1], attr)
                except curses.error:
                    pass

        def draw_header():
            hy = HEADER_TOP
            for li, line in enumerate(LOGO):
                put(hy + li, PAD, line, C_HDR)
            # tabs debajo del logo (con una línea de separación)
            ty = hy + len(LOGO) + 1
            tx = PAD
            for tm, tl in [(MODE_SESSIONS, "Sesiones"), (MODE_HISTORY, "Historial"), (MODE_ARCHIVED, "Archivadas")]:
                active = tm == mode
                if active:
                    put(ty, tx,     "┤", C_HDR)
                    put(ty, tx + 1, f" {tl} ", C_HDR)
                    put(ty, tx + 2 + len(tl), "├", C_HDR)
                    tx += len(tl) + 4
                else:
                    lbl = f"  {tl}  "
                    put(ty, tx, lbl, C_TAB)
                    tx += len(lbl)
            put(ty + 1, PAD, "─" * (w - 1 - PAD), C_DIM)

        def draw_history_tab() -> tuple:
            """Dibuja el tab de historial. Retorna (footer, filtered, cs)."""
            nonlocal scroll
            items      = rows
            active_ids = extra
            if query:
                q        = query.lower()
                filtered = [it for it in items
                            if q in it["first_msg"].lower()
                            or q in os.path.basename(it["project"]).lower()]
            else:
                filtered = items
            cs = min(cursor, max(0, len(filtered) - 1))

            h, w = stdscr.getmaxyx()
            put(list_y,     PAD, "🔍 ", C_SRCH)
            put(list_y,     PAD + 3, (query + "▌")[:w - PAD - 4], C_SRCH)
            put(list_y + 1, PAD, "─" * (w - 1 - PAD), C_DIM)
            put(list_y + 2, PAD, f"  {len(filtered)}/{len(items)} conversaciones", C_DIM)

            iy  = list_y + 3
            vis = h - iy - 2
            sc  = scroll
            if cs < sc:
                sc = cs
            elif cs >= sc + vis:
                sc = cs - vis + 1
            scroll = sc

            for i, item in enumerate(filtered[sc:sc + vis]):
                ri    = i + sc
                sid   = item["sessionId"]
                proj  = os.path.basename(item["project"]) if item["project"] else "?"
                msg   = item["first_msg"][:max(0, w - 50)].replace("\n", " ")
                date  = fmt_ts(item["last_ts"])
                tic   = "🟢 " if sid in active_ids else "   "
                cnt   = f"({item['count']})"
                ic    = ri == cs
                pre   = " ❯ " if ic else "   "
                attr  = C_CUR if ic else (C_RUN if sid in active_ids else C_NORM)
                put(iy + i, PAD, f"{pre}{tic}{proj:<18} {date:<12} {cnt:<5} {msg}", attr)

            footer = "  [↑↓/jk] navegar  [↵] abrir  [⇥/⇤] pestaña  [q/ESC] salir  [⌫] borrar búsqueda"
            return footer, filtered, cs

        def draw_sessions_tab() -> tuple:
            """Dibuja el tab de sesiones/archivadas. Retorna (footer, sidx, cs, sel)."""
            nonlocal scroll
            sr   = rows
            sl   = extra
            sidx = [i for i, r in enumerate(sr) if r[1]]
            cs   = min(cursor, max(0, len(sidx) - 1))
            h, w = stdscr.getmaxyx()
            vis  = h - list_y - 2

            if sidx:
                ac = sidx[cs]
                if ac < scroll:
                    scroll = ac
                elif ac >= scroll + vis:
                    scroll = ac - vis + 1

            if not sr:
                put(list_y + 2, PAD + 2,
                    "No hay sesiones en el registry." if mode == MODE_SESSIONS
                    else "No hay sesiones archivadas.", C_DIM)
            else:
                for i in range(min(vis, len(sr) - scroll)):
                    ri   = scroll + i
                    if ri >= len(sr):
                        break
                    row  = sr[ri]
                    line = sl[ri]
                    if not line:
                        continue
                    is_sel  = row[1]
                    is_att  = row[2] if len(row) > 2 else False
                    is_run  = row[3] if len(row) > 3 else False
                    is_cur  = is_sel and bool(sidx) and sidx[cs] == ri
                    row_type = row[4] if len(row) > 4 else "group"
                    if not is_sel and row_type == "pane":
                        # sub-agente del team — más indentado, color dim
                        put(list_y + i, 9, line.lstrip(), C_DIM)
                    elif not is_sel:
                        # group header — alineado con el header bar
                        put(list_y + i, PAD, line.lstrip(), C_RUN)
                    else:
                        # line item — indentado dentro del grupo
                        if is_cur:
                            pre, attr = " ❯ ", C_CUR
                        elif mode == MODE_ARCHIVED:
                            pre, attr = "   ", C_ARCH
                        elif is_att or is_run:
                            pre, attr = "   ", C_ACTIVE
                        else:
                            pre, attr = "   ", C_NORM
                        put(list_y + i, 5, pre + line.lstrip(), attr)

            sel    = sr[sidx[cs]][0] if sidx else None
            footer = ("  [↵] attach  [n] nueva  [r] renombrar  [a] archivar  [x] restart  [d] eliminar  [⇥/⇤] pestaña  [q] salir"
                      if mode == MODE_SESSIONS
                      else "  [↵] restaurar  [d] eliminar  [⇥/⇤] pestaña  [q] salir")
            return footer, sidx, cs, sel

        def draw_overlays(footer: str) -> str:
            """Dibuja barras de overlay (prompts/confirmaciones). Retorna footer actualizado."""
            h, w = stdscr.getmaxyx()
            if new_sess_prompt:
                put(h - 2, PAD, "─" * (w - 1 - PAD), C_DIM)
                put(h - 2, PAD, f"  ✦  Nueva sesión: {new_sess_buf}▌", C_SRCH)
                footer = "  [↵] crear  [ESC] cancelar"
            if name_prompt:
                put(h - 2, PAD, "─" * (w - 1 - PAD), C_DIM)
                put(h - 2, PAD, f"  💬 Nombre de sesión: {name_buf}▌", C_SRCH)
                footer = "  [↵] confirmar  [ESC] cancelar"
            if rename_on:
                put(h - 2, PAD, "─" * (w - 1 - PAD), C_DIM)
                put(h - 2, PAD, f"  ✏  Renombrar → {rename_buf}▌", C_SRCH)
                footer = "  [↵] confirmar  [ESC] cancelar"
            if restart_target:
                short = restart_target.removeprefix(SESSION_PREFIX + "-")
                put(h - 2, PAD, "─" * (w - 1 - PAD), C_DIM)
                put(h - 2, PAD, f"  ↺  ¿Reiniciar '{short}'? (s/N)", C_CUR | curses.A_BOLD)
                footer = "  [s/y] confirmar  [N] cancelar"
            if del_target:
                short = del_target.removeprefix(SESSION_PREFIX + "-")
                put(h - 2, PAD, "─" * (w - 1 - PAD), C_DIM)
                put(h - 2, PAD, f"  ⚠  ¿Eliminar '{short}'? (s/N)", C_ARCH | curses.A_BOLD)
                footer = "  [s/y] confirmar  [N] cancelar"
            return footer

        list_y = HEADER_TOP + len(LOGO) + 3

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()

            draw_header()

            if mode == MODE_HISTORY:
                footer, filtered, cs = draw_history_tab()
            else:
                footer, sidx, cs, sel = draw_sessions_tab()

            footer = draw_overlays(footer)
            put(h - 1, PAD, footer, C_HELP)
            stdscr.refresh()

            key = stdscr.getch()

            # ── overlay input handlers ──

            # new session input
            if new_sess_prompt:
                if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    name = new_sess_buf.strip().replace(" ", "-") or None
                    new_sess_prompt = False; new_sess_buf = ""
                    if name:
                        pending[0] = ("new_session", name)
                        break
                elif key == 27:
                    new_sess_prompt = False; new_sess_buf = ""
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    new_sess_buf = new_sess_buf[:-1]
                elif 32 <= key <= 126 and chr(key) not in "/":
                    new_sess_buf += chr(key)
                continue

            # restart confirm
            if restart_target:
                if key in (ord("s"), ord("S"), ord("y"), ord("Y")):
                    name = restart_target.removeprefix(SESSION_PREFIX + "-")
                    restart_target = None
                    pending[0] = ("restart_session", f"{SESSION_PREFIX}-{name}")
                    break
                else:
                    restart_target = None
                continue

            # delete confirm
            if del_target:
                if key in (ord("s"), ord("S"), ord("y"), ord("Y")):
                    dashboard_delete_session(del_target, from_archived=del_arch)
                    del_target = None
                    refresh()
                else:
                    del_target = None
                continue

            # name prompt input (historial)
            if name_prompt:
                if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    pending[0] = ("open_history_named", name_item, name_buf or f"chat-{name_item['sessionId'][:6]}")
                    break
                elif key == 27:
                    name_prompt = False; name_buf = ""; name_item = None
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    name_buf = name_buf[:-1]
                elif 32 <= key <= 126 and chr(key) not in "/":
                    name_buf += chr(key)
                continue

            # rename input
            if rename_on:
                if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    if rename_buf and rename_target:
                        dashboard_rename_session(rename_target, rename_buf)
                    rename_on = False; rename_buf = ""; rename_target = None
                    refresh()
                elif key == 27:
                    rename_on = False; rename_buf = ""; rename_target = None
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    rename_buf = rename_buf[:-1]
                elif 32 <= key <= 126 and chr(key) not in " /":
                    rename_buf += chr(key)
                continue

            # ── tab navigation ──
            _MODES = [MODE_SESSIONS, MODE_HISTORY, MODE_ARCHIVED]
            if key == ord("\t"):
                mode = _MODES[(_MODES.index(mode) + 1) % len(_MODES)]
                cursor = 0; scroll = 0; query = ""
                rows, extra = load_data()
                continue
            elif key == curses.KEY_BTAB:
                mode = _MODES[(_MODES.index(mode) - 1) % len(_MODES)]
                cursor = 0; scroll = 0; query = ""
                rows, extra = load_data()
                continue

            # ── history navigation ──
            if mode == MODE_HISTORY:
                flt = filtered
                if key in (curses.KEY_UP, ord("k")) and cursor > 0:
                    cursor -= 1
                elif key in (curses.KEY_DOWN, ord("j")) and cursor < len(flt) - 1:
                    cursor += 1
                elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    if flt:
                        item = flt[cs]
                        proj = os.path.basename(item["project"]) if item["project"] else "chat"
                        name_prompt = True
                        name_item   = item
                        name_buf    = f"{proj}-{item['sessionId'][:6]}"
                elif key in (ord("q"), 27):
                    mode = MODE_SESSIONS; cursor = 0; scroll = 0; query = ""
                    rows, extra = build_session_rows()
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    query = query[:-1]; cursor = 0; scroll = 0
                elif 32 <= key <= 126:
                    query += chr(key); cursor = 0; scroll = 0
                continue

            # ── sessions / archived navigation ──
            if key in (curses.KEY_UP, ord("k")) and cursor > 0:
                cursor -= 1
            elif key in (curses.KEY_DOWN, ord("j")) and cursor < len(sidx) - 1:
                cursor += 1
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                if sel:
                    if mode == MODE_ARCHIVED:
                        dashboard_unarchive_session(sel); refresh()
                    else:
                        pending[0] = ("open_session", sel); break
            elif key == ord("r") and mode == MODE_SESSIONS and sel:
                rename_on = True; rename_target = sel
                rename_buf = sel.removeprefix(SESSION_PREFIX + "-")
            elif key == ord("x") and mode == MODE_SESSIONS and sel:
                restart_target = sel
            elif key == ord("n") and mode == MODE_SESSIONS:
                new_sess_prompt = True; new_sess_buf = ""
            elif key == ord("a") and mode == MODE_SESSIONS and sel:
                dashboard_archive_session(sel); refresh()
            elif key == ord("d") and sel:
                del_target = sel; del_arch = (mode == MODE_ARCHIVED)
            elif key in (ord("q"), 27):
                break

    try:
        curses.wrapper(_ui)
    except KeyboardInterrupt:
        pass

    if pending[0]:
        p = pending[0]
        action = p[0]
        if action == "restart_session":
            name = p[1].removeprefix(SESSION_PREFIX + "-")
            cmd_restart(name)
        elif action == "new_session":
            name  = p[1]
            cwd   = os.getcwd()
            group = detect_group(cwd)
            cmd_start(name, group, None, cwd)
        elif action == "open_session":
            dashboard_open_session(p[1])
        elif action in ("open_history", "open_history_named"):
            item         = p[1]
            custom_name  = p[2] if action == "open_history_named" else None
            sid          = item["sessionId"]
            project_path = item["project"] or os.getcwd()
            project      = os.path.basename(project_path) if project_path else "chat"
            active_ids   = get_active_conv_ids()
            if sid in active_ids:
                reg = registry_load()
                for sname, info in reg["sessions"].items():
                    if info.get("resume_id") == sid and tmux_has_session(sname):
                        os.execlp("tmux", "tmux", "attach", "-t", sname)
                        return
            short_id = sid[:6]
            name     = custom_name if custom_name else f"{project}-{short_id}"
            group    = detect_group(project_path) if os.path.isdir(project_path) else project
            cmd_start(name, group, sid, project_path)
