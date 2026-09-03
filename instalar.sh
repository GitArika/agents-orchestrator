#!/usr/bin/env bash
# Instalação do orquestrador. Idempotente: rodar de novo é o caminho de
# atualização, não um risco.
#
#   ./instalar.sh              instala ou atualiza
#   ./instalar.sh --simular    mostra tudo e não escreve nada
#   ./instalar.sh --sem-skills não mexe em ~/.claude/skills
#   ./instalar.sh --bin-dir D  liga os executáveis em D
#
# Nada é copiado: os executáveis e as skills são LIGADOS para dentro do
# repositório clonado. Assim `git pull` atualiza tudo de uma vez e nada
# envelhece em silêncio numa cópia esquecida.
set -uo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
SIMULAR=0; SEM_SKILLS=0; BIN_DIR="$HOME/.local/bin"; SUBSTITUIR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --simular) SIMULAR=1; shift ;;
    --sem-skills) SEM_SKILLS=1; shift ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --substituir-instalacao) SUBSTITUIR=1; shift ;;
    *) echo "opção desconhecida: $1"; exit 2 ;;
  esac
done

titulo() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()     { printf '  \033[32m✓\033[0m %s\n' "$*"; }
aviso()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
erro()   { printf '  \033[31m✗\033[0m %s\n' "$*"; }
parar()  { printf '\n\033[31mPAREI.\033[0m %s\n\n' "$*"; exit 1; }
faria()  { [ "$SIMULAR" = 1 ] && { printf '  \033[2m→ faria: %s\033[0m\n' "$*"; return 0; }; return 1; }

# ── 1. segredo dentro do repositório ────────────────────────────────────────
# Um repositório que vai para o GitHub interno não pode ter segredo dentro, e a
# hora de descobrir isso é antes de instalar — não depois de publicar.
titulo "Segredo dentro do repositório"
ACHADOS="$(grep -rIlE 'pk_[0-9]{6,}_[A-Z0-9]{20,}|xox[baprs]-|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}' \
  --exclude-dir=.git --exclude='*.exemplo' "$AQUI" 2>/dev/null || true)"
if [ -n "$ACHADOS" ]; then
  erro "parece haver segredo nestes arquivos:"
  printf '%s\n' "$ACHADOS" | sed 's/^/      /'
  parar "Remova antes de instalar. Credencial vive em ~/.config/orquestrador/."
fi
ok "nenhum segredo na árvore"

# ── 2. pré-requisitos, provados por chamada ─────────────────────────────────
titulo "Pré-requisitos (provados por chamada, não por declaração)"
for f in git python3 node; do
  command -v "$f" >/dev/null || parar "falta $f."
  ok "$f  $($f --version 2>&1 | head -1)"
done
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[ "$NODE_MAJOR" -ge 20 ] || parar "node 20 ou mais novo é necessário (achei $NODE_MAJOR)."
command -v tmux >/dev/null && ok "tmux  $(tmux -V)" || aviso "sem tmux: as sessões rodam soltas, sem 'orq attach'"
command -v docker >/dev/null && ok "docker presente (o ambiente fechado vai precisar)" \
  || aviso "sem docker: o ambiente fechado de testes não sobe nesta máquina"

if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  erro "CLAUDE_CODE_OAUTH_TOKEN está no ambiente"
  parar "Essa variável vence o login interativo, DESLIGA o acompanhamento remoto e
  REBAIXA o modelo do seu plano. Remova-a do perfil do shell e autentique
  rodando 'claude' uma vez."
fi

command -v claude >/dev/null || parar "falta o Claude Code (claude) na PATH."
printf '  \033[2m… perguntando ao agente (isto demora alguns segundos)\033[0m\n'
RESP="$(claude -p 'responda apenas: ok' 2>&1 | tr '[:upper:]' '[:lower:]')"
case "$RESP" in
  *ok*) ok "o agente respondeu" ;;
  *) erro "o agente não respondeu"
     printf '      %s\n' "$(printf '%s' "$RESP" | head -3)"
     parar "Autentique com 'claude' e rode isto de novo. Não adianta seguir:
  cada sessão morreria dois segundos depois de nascer, e o quadro ficaria
  marcado como se alguém estivesse trabalhando." ;;
esac

# ── 3. executáveis na PATH ──────────────────────────────────────────────────
titulo "Executáveis"
CONFLITO=""
for exe in orq orq-clickup orq-avisar orq-ram orq-medir; do
  atual="$(command -v "$exe" 2>/dev/null || true)"
  if [ -n "$atual" ]; then
    destino="$(readlink -f "$atual" 2>/dev/null || echo "$atual")"
    case "$destino" in "$AQUI"/*) ;; *) CONFLITO="$CONFLITO$exe → $destino"$'\n' ;; esac
  fi
done
if [ -n "$CONFLITO" ] && [ "$SUBSTITUIR" != 1 ]; then
  erro "já existe outra instalação na sua PATH:"
  printf '%s' "$CONFLITO" | sed 's/^/      /'
  parar "Ela pode estar governando uma esteira AGORA — trocar o caminho por baixo
  de sessões vivas é a forma mais rápida de perder trabalho em voo.

  Antes de substituir: pare o laço ('orq loop-stop'), confira que não há
  sessão viva ('orq status') e então repita com --substituir-instalacao."
fi

if ! faria "mkdir -p $BIN_DIR"; then mkdir -p "$BIN_DIR"; fi
for exe in orq orq-clickup orq-avisar orq-ram orq-medir; do
  if faria "ln -sf $AQUI/bin/$exe $BIN_DIR/$exe"; then continue; fi
  ln -sf "$AQUI/bin/$exe" "$BIN_DIR/$exe" && ok "$exe → $BIN_DIR/$exe"
done
case ":$PATH:" in
  *":$BIN_DIR:"*) ok "$BIN_DIR já está na sua PATH" ;;
  *) aviso "$BIN_DIR NÃO está na sua PATH. Acrescente ao seu perfil:"
     printf '        export PATH="%s:$PATH"\n' "$BIN_DIR"
     aviso "as sessões chamam 'orq advance' por conta própria — sem isso elas não conseguem" ;;
esac

# ── 4. skills ───────────────────────────────────────────────────────────────
titulo "Skills"
if [ "$SEM_SKILLS" = 1 ]; then
  aviso "pulado por --sem-skills"
else
  DEST_SKILLS="$HOME/.claude/skills"
  if ! faria "mkdir -p $DEST_SKILLS"; then mkdir -p "$DEST_SKILLS"; fi
  n=0
  for d in "$AQUI"/skills/*/; do
    [ -d "$d" ] || continue
    nome="$(basename "$d")"
    if faria "ln -sfn $d $DEST_SKILLS/$nome"; then n=$((n+1)); continue; fi
    ln -sfn "${d%/}" "$DEST_SKILLS/$nome" && n=$((n+1))
  done
  [ "$n" -gt 0 ] && ok "$n skill(s) ligada(s) em $DEST_SKILLS" \
                 || aviso "nenhuma skill no repositório ainda"
fi

# ── 5. credencial ───────────────────────────────────────────────────────────
titulo "Credencial do ClickUp"
CRED_DIR="$HOME/.config/orquestrador"
CRED="$CRED_DIR/credenciais.env"
if [ -f "$CRED" ]; then
  ok "já existe: $CRED"
  [ "$(stat -f %Lp "$CRED" 2>/dev/null || stat -c %a "$CRED" 2>/dev/null)" = "600" ] \
    || { aviso "permissão frouxa; ajustando para 600"; faria "chmod 600 $CRED" || chmod 600 "$CRED"; }
else
  if faria "criar $CRED a partir do exemplo, com permissão 600"; then :; else
    mkdir -p "$CRED_DIR"; chmod 700 "$CRED_DIR"
    cp "$AQUI/modelos/credenciais.env.exemplo" "$CRED"; chmod 600 "$CRED"
    aviso "criado a partir do exemplo — ABRA e ponha o seu token:"
    printf '        %s\n' "$CRED"
    aviso "o token é PESSOAL: tudo que a esteira escrever aparece como escrito por você"
  fi
fi

# ── 6. a cerca ──────────────────────────────────────────────────────────────
titulo "Cerca de permissões"
CERCA="$AQUI/hooks/cerca.sh"
[ -x "$CERCA" ] || parar "a cerca sumiu ou não é executável: $CERCA
  Nenhuma sessão sobe sem ela. Restaure: git -C $AQUI checkout hooks/cerca.sh"
if [ -x "$AQUI/testes/cerca.sh" ]; then
  if "$AQUI/testes/cerca.sh" >/dev/null 2>&1; then
    ok "a cerca barra e deixa passar o que deve (bateria de casos verde)"
  else
    parar "a bateria da cerca FALHOU. Uma cerca com defeito deixa tudo passar e
  dá confiança falsa. Rode para ver: $AQUI/testes/cerca.sh"
  fi
fi

# ── 7. pré-voo ──────────────────────────────────────────────────────────────
titulo "Pré-voo"
if [ "$SIMULAR" = 1 ]; then
  printf '  \033[2m→ faria: orq doctor (dentro de um projeto com esteira)\033[0m\n'
  printf '\n\033[1mSimulação encerrada. Nada foi escrito.\033[0m\n\n'
  exit 0
fi
printf '\n\033[1mInstalado.\033[0m Agora, de dentro de um projeto:\n\n'
printf '  orq init          cria a esteira daquele projeto, a partir do que ele é\n'
printf '  orq doctor        prova que está tudo de pé, por chamada real\n'
printf '  orq board         o quadro\n\n'
