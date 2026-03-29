# claude-tmux

**Run multiple Claude Code agents in parallel — one tmux session per project, zero context switching.**

`claude-tmux` is a lightweight session manager that wraps [Claude Code](https://claude.ai/code) inside tmux. Start agents across dozens of repos, switch between them instantly, and never lose a conversation — even after a server reboot.

---

## Why claude-tmux?

Working with Claude Code on multiple projects means constant interruption: closing one chat, navigating to another directory, starting a new session, losing track of where you left off. `claude-tmux` eliminates that friction.

- **One command** to launch a Claude agent for any project
- **Persistent sessions** that survive disconnects, reboots, and crashes
- **Auto-restart loop** so Ctrl+C never loses your work — Claude comes right back
- **Compaction-aware** — when Claude starts a new conversation ID after compaction, the registry updates automatically so `--resume` always points to the right place
- **Visual dashboard** to see every agent at a glance, attach in one keystroke, or browse the full conversation history

---

## Features

| Feature | Description |
|---|---|
| **Interactive TUI dashboard** | Three tabs: Sessions / History / Archived — navigate with keyboard |
| **Project grouping** | Auto-detects Git root to group sessions by repo |
| **Auto-restart on crash** | Ctrl+C kills Claude, the wrapper loop relaunches it immediately |
| **Compaction tracking** | Detects session ID changes after context compaction and syncs the registry |
| **Persistent registry** | `~/.config/claude-tmux/registry.json` — survives server reboots |
| **`restore` command** | Recreates all tmux sessions from the registry after a reboot |
| **`restart` command** | Kills and recreates a stuck session without losing registry state |
| **`kill` command** | Terminates a tmux session while keeping it in the registry |
| **History browser** | Browse past Claude conversations, search by project, and reopen any of them |
| **Archive** | Move sessions out of the way without deleting them |

---

## Installation

```bash
curl -o ~/.local/bin/claude-tmux \
  https://raw.githubusercontent.com/davidsuarezcdo/claude-tmux/main/claude-tmux
chmod +x ~/.local/bin/claude-tmux
```

Or clone and symlink:

```bash
git clone https://github.com/davidsuarezcdo/claude-tmux.git
ln -s "$PWD/claude-tmux/claude-tmux" ~/.local/bin/claude-tmux
```

**Requirements:** Python 3.10+, `tmux`, `git`

---

## Quick Start

```bash
# Open the dashboard
claude-tmux list

# Start a Claude agent in the current directory
claude-tmux start

# Start with a custom name and project group
claude-tmux start my-feature --group my-repo

# Resume a previous conversation by ID
claude-tmux start --resume 4496dd73-...

# Browse conversation history and reopen any session
claude-tmux history

# Reconnect to a running session
claude-tmux attach my-feature
```

---

## Dashboard

The TUI dashboard gives you a live view of every agent and project.

```
▌ claude-tmux  ┤ Sesiones ├  Historial   Archivadas
─────────────────────────────────────────────────────────────────

  ◆ heroes-tickets
    ▶ tickets-cobranza      ~/repos/heroes-tickets  03/28  3
    ● sync-pagos            ~/repos/heroes-tickets  03/27  1

  ◆ another-project
    ○ refactor-api          ~/repos/another-project 03/26  5

  [↑↓/jk] navegar  [↵] attach  [⇥/⇤] pestaña  [q] salir
```

### Session Icons

| Icon | Meaning |
|------|---------|
| `▶` | Active and attached (you are connected) |
| `●` | Running in the background |
| `○` | In registry only (tmux session not running) |
| `▣` | Archived |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑↓` / `jk` | Navigate |
| `Enter` | Attach to session |
| `Tab` / `Shift+Tab` | Switch tabs |
| `r` | Rename session |
| `a` | Archive session |
| `x` | Restart session (kill + recreate) |
| `d` | Delete session |
| `q` / `ESC` | Quit |

The **History tab** lets you search all past Claude conversations and open any of them as a new named session.

---

## Commands

```
claude-tmux start [name] [--group GROUP] [--resume ID]
claude-tmux list
claude-tmux attach <name>
claude-tmux history
claude-tmux restore [--attach]
claude-tmux kill <name>
claude-tmux restart <name> [--no-attach]
claude-tmux upgrade
```

| Command | Description |
|---------|-------------|
| `start` | Create a new Claude session in the current directory |
| `list` | Open the TUI dashboard |
| `attach` | Connect to an existing session |
| `history` | Browse and reopen past conversations |
| `restore` | Recreate all sessions from the registry (e.g. after reboot) |
| `kill` | Terminate a tmux session, keep it in the registry |
| `restart` | Kill and recreate a stuck session from the registry |
| `upgrade` | Update claude-tmux to the latest version from GitHub |

---

## How It Works

Each session runs Claude inside a `bash` loop:

```
bash loop
  └── claude --dangerously-skip-permissions [--resume ID]
        ↓ exits (Ctrl+C, /exit, crash)
  └── claude-tmux _sync-id  ← detects compaction, updates registry
  └── sleeps 0.5s, reads fresh resume_id
  └── relaunches Claude
```

This means:
- **Ctrl+C** interrupts Claude, not your session — the loop relaunches it
- After **context compaction**, the new session ID is automatically saved to the registry
- On next restart, `--resume` always points to the latest conversation

The registry at `~/.config/claude-tmux/registry.json` stores the full ID chain for every session:

```json
{
  "sessions": {
    "claude-tickets-cobranza": {
      "group": "heroes-tickets",
      "path": "/home/user/repos/heroes-tickets",
      "created": "2026-03-17T10:00:00",
      "resume_id": "4496dd73-...",
      "id_chain": ["previous-id-..."]
    }
  }
}
```

---

## Tips

**Run agents on many repos at once** — start a session per repo and use the dashboard to jump between them. Each agent has full context for its project.

**After a server reboot**, run `claude-tmux restore --attach` to bring everything back. The first session opens immediately; the rest recreate in the background.

**Stuck session?** Use `x` in the dashboard or `claude-tmux restart <name>` to kill the tmux session and recreate it from the registry — no need to configure anything again.

**Browse history without opening a session** — the History tab searches `~/.claude/history.jsonl` across all projects. Press Enter on any entry to open it as a new named session.

---

## License

MIT
