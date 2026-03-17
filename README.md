# claude-tmux

Gestiona sesiones de [Claude Code](https://claude.ai/code) con tmux. Cada proyecto es una sesión, cada chat una ventana. Incluye dashboard TUI, historial de conversaciones, auto-reinicio en Ctrl+C y seguimiento de IDs tras compactación.

## Características

- **Dashboard interactivo** (curses) con 3 tabs: Sesiones / Historial / Archivadas
- **Agrupación por proyecto** — auto-detecta el repo git como grupo
- **Auto-reinicio** — Ctrl+C solo mata Claude, el loop lo relanza automáticamente
- **Seguimiento de compactación** — detecta cuando Claude cambia de sessionId y actualiza el registry
- **Registry persistente** en `~/.config/claude-tmux/registry.json` — sobrevive reinicios del servidor
- **`restore`** — recrea todas las sesiones tmux desde el registry tras un reboot
- `--dangerously-skip-permissions` por defecto en todas las sesiones

## Instalación

```bash
# Copiar el script a tu PATH
cp claude-tmux ~/.local/bin/claude-tmux
chmod +x ~/.local/bin/claude-tmux
```

## Uso

```bash
# Abrir dashboard (sesiones activas)
claude-tmux list

# Nueva sesión desde el directorio actual
claude-tmux start

# Nueva sesión con nombre y grupo explícito
claude-tmux start mi-chat --group heroes-tickets

# Reanudar conversación por ID
claude-tmux start --resume 4496dd73-...

# Explorar historial de Claude y abrir desde ahí
claude-tmux history

# Restaurar todas las sesiones tras reinicio del servidor
claude-tmux restore --attach

# Reconectar a sesión existente
claude-tmux attach heroes-tickets
```

## Dashboard

```
  🤖  1 Sesiones   2 Historial   3 Archivadas
──────────────────────────────────────────────

  ◆ heroes-tickets  ~/compara/repos
    ▶ tickets-cobranza         ~/compara/repos/heroes-tickets
    ● sync-pagos               ~/compara/repos/heroes-tickets

  ◆ otro-proyecto  ~/compara/repos
    ○ refactor-api             ~/compara/repos/otro-proyecto

  Enter attach   r renombrar   a archivar   d eliminar   2 hist   q salir
```

**Iconos de sesión:**
| Icono | Significado |
|-------|-------------|
| `▶`   | Activa y conectada (attached) |
| `●`   | Corriendo en background |
| `○`   | Solo en registry (tmux no activo) |
| `▣`   | Archivada |

## Atajos del dashboard

| Tecla | Acción |
|-------|--------|
| `↑↓` / `jk` | Navegar |
| `Enter` | Attach / abrir |
| `r` | Renombrar sesión |
| `a` | Archivar sesión |
| `d` | Eliminar sesión |
| `1/2/3` | Cambiar tab |
| `q` / `ESC` | Salir |

En el **tab Historial**, al presionar Enter se pide el nombre que tendrá la nueva sesión tmux (pre-rellenado con `proyecto-shortid`).

## Registry

Guardado en `~/.config/claude-tmux/registry.json`. Estructura:

```json
{
  "sessions": {
    "claude-tickets-cobranza": {
      "group": "heroes-tickets",
      "path": "/home/david/compara/repos/heroes-tickets",
      "created": "2026-03-17T10:00:00",
      "resume_id": "4496dd73-...",
      "id_chain": ["anterior-id-..."]
    }
  },
  "conversations": {},
  "archived": {}
}
```

## Dependencias

- Python 3.10+
- `tmux`
- `git` (para auto-detectar grupos)
- `fzf` (opcional — fallback a curses si no está disponible)
