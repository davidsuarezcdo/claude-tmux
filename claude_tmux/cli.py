import argparse
import os
import sys

from .session import (
    cmd_start, cmd_chat, cmd_attach, cmd_save, cmd_resume,
    cmd_convs, cmd_restore, cmd_kill, cmd_restart, cmd_upgrade,
    cmd_get_resume_id, cmd_sync_id,
    build_session_rows,
)
from .history import cmd_history
from .dashboard import run_dashboard, MODE_SESSIONS


def cmd_list(interactive: bool = True) -> None:
    if not interactive:
        rows, lines = build_session_rows()
        if not rows:
            print("No hay sesiones en el registry.")
            return
        for line in lines:
            print(line)
        print()
        return
    run_dashboard(MODE_SESSIONS)


def main() -> None:
    # Comandos internos (usados por build_tmux_cmd, no aparecen en --help)
    if len(sys.argv) >= 2:
        if sys.argv[1] == "_sync-id" and len(sys.argv) >= 4:
            cmd_sync_id(sys.argv[2], int(sys.argv[3]))
            return
        if sys.argv[1] == "_get-resume-id" and len(sys.argv) >= 3:
            cmd_get_resume_id(sys.argv[2])
            return

    parser = argparse.ArgumentParser(
        prog="claude-tmux",
        description="Gestiona sesiones tmux de Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", metavar="comando")

    # start
    p_start = sub.add_parser("start", help="Crear o reconectar sesión")
    p_start.add_argument("name", nargs="?", help="Nombre del chat (default: dirname)")
    p_start.add_argument("--group", "-g", metavar="GRUPO", help="Grupo/proyecto (default: git repo name)")
    p_start.add_argument("--path", "-p", metavar="PATH", help="Directorio del proyecto (override)")
    p_start.add_argument("--resume", metavar="ID", help="Reanudar conversación por ID")

    # chat
    p_chat = sub.add_parser("chat", help="Nueva ventana Claude en sesión actual")
    p_chat.add_argument("--resume", metavar="ID", help="Reanudar conversación por ID")

    # list
    p_list = sub.add_parser("list", help="Listar sesiones Claude (interactivo, Enter=attach)")
    p_list.add_argument("--plain", action="store_true", help="Solo imprimir, sin interacción")

    # attach
    p_attach = sub.add_parser("attach", help="Reconectar a sesión existente")
    p_attach.add_argument("name", help="Nombre de la sesión")

    # save
    p_save = sub.add_parser("save", help="Guardar ID de conversación con un nombre")
    p_save.add_argument("name", help="Nombre para identificar la conversación")
    p_save.add_argument("id", metavar="SESSION_ID", help="ID de conversación de Claude")
    p_save.add_argument("--path", "-p", metavar="PATH", help="Directorio del proyecto (default: cwd)")
    p_save.add_argument("--group", "-g", metavar="GRUPO", help="Grupo/proyecto")

    # resume
    p_resume = sub.add_parser("resume", help="Retomar conversación guardada por nombre")
    p_resume.add_argument("name", help="Nombre de la conversación guardada")

    # convs
    sub.add_parser("convs", help="Listar conversaciones guardadas")

    # restore
    p_restore = sub.add_parser("restore", help="Restaurar sesiones tmux desde el registry")
    p_restore.add_argument("--attach", "-a", action="store_true", help="Hacer attach a la primera sesión restaurada")

    # history
    sub.add_parser("history", help="Explorar historial de Claude con búsqueda")

    # kill
    p_kill = sub.add_parser("kill", help="Terminar sesión tmux sin borrarla del registry")
    p_kill.add_argument("name", help="Nombre de la sesión")

    # restart
    p_restart = sub.add_parser("restart", help="Matar y recrear sesión atascada desde el registry")
    p_restart.add_argument("name", help="Nombre de la sesión")
    p_restart.add_argument("--no-attach", action="store_true", help="No hacer attach después de recrear")

    # upgrade
    sub.add_parser("upgrade", help="Actualizar claude-tmux a la última versión desde GitHub")

    args = parser.parse_args()

    if args.cmd == "start":
        cmd_start(args.name, args.group, args.resume, args.path)
    elif args.cmd == "chat":
        cmd_chat(args.resume)
    elif args.cmd == "list":
        cmd_list(interactive=not args.plain)
    elif args.cmd == "attach":
        cmd_attach(args.name)
    elif args.cmd == "save":
        cmd_save(args.name, args.id, args.path, args.group)
    elif args.cmd == "resume":
        cmd_resume(args.name)
    elif args.cmd == "convs":
        cmd_convs()
    elif args.cmd == "history":
        cmd_history()
    elif args.cmd == "restore":
        cmd_restore(attach_first=args.attach)
    elif args.cmd == "kill":
        cmd_kill(args.name)
    elif args.cmd == "restart":
        cmd_restart(args.name, no_attach=args.no_attach)
    elif args.cmd == "upgrade":
        cmd_upgrade()
    else:
        parser.print_help()
