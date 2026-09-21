#!/usr/bin/env bash
# Orchestrator notification hook. Reads a hook event on stdin and raises a macOS
# notification so an unattended session that needs a human is never silent.
# Wired via --settings at launch; never mutates the repo's own settings.
set -uo pipefail

UNIT="${ORQ_UNIT:-claude}"
KIND="${1:-notify}"
LOGDIR="${ORQ_LOG_DIR:-$HOME/.claude/orchestrator/state}"
mkdir -p "$LOGDIR"
# O rótulo vai para nome de arquivo: barras e espaços viram hífen.
SAFE="$(printf '%s' "$UNIT" | tr '/ ' '--' | tr -cd 'A-Za-z0-9._-')"

payload="$(cat 2>/dev/null || true)"

field() { printf '%s' "$payload" | /usr/bin/python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
v=d.get('$1') or ''
print(str(v).replace(chr(10),' ')[:180])
" 2>/dev/null; }

msg="$(field message)"
[ -z "$msg" ] && msg="$(field prompt)"

case "$KIND" in
  notification) title="⚠️ $UNIT precisa de você"; [ -z "$msg" ] && msg="A sessão está aguardando uma decisão." ;;
  stop)         title="⏹ $UNIT encerrou o turno";  [ -z "$msg" ] && msg="Confira o board: orq status" ;;
  *)            title="🔔 $UNIT" ;;
esac

printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$KIND" "${msg:0:300}" >> "$LOGDIR/${SAFE}.events"

# Entrega. O registro acima é o canal que sempre existe; daqui para baixo é
# best-effort e nunca pode falhar o hook (o Claude Code trata saída != 0 do hook
# como erro do turno). $ORQ_NOTIFY_CMD atende host sem desktop — a VPS, por ex.
# O entregador do repositório é o padrão. Ele conhece os três destinos e nunca
# derruba quem chamou; $ORQ_NOTIFY_CMD continua vencendo, para quem já montou o
# próprio caminho.
ENTREGADOR="${ORQ_NOTIFY_CMD:-$(cd "$(dirname "$0")/../bin" && pwd)/orq-avisar}"
ORQ_NOTIFY_TITLE="$title" ORQ_NOTIFY_MSG="$msg" \
  $ENTREGADOR "$title" "$msg" >/dev/null 2>&1 || true
exit 0
