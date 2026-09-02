#!/usr/bin/env bash
# A cerca. Roda ANTES de cada uso de ferramenta e pode barrar (código 2).
#
# POR QUE UM GANCHO, E NÃO UMA LISTA DE NEGAÇÃO NO ARQUIVO DE CONFIGURAÇÃO:
# provado em 02/09/2026 contra o Claude Code 2.1.252. Uma negação
# `Bash(git push:*)` vinda por --settings NÃO venceu um `allow` idêntico que a
# pessoa já tinha nas próprias configurações: o comando executou. E regra por
# prefixo nunca pega `cd /outro/lugar && git push`, que é uma linha de shell
# comum. O gancho vê o comando inteiro, roda sempre, e não é anulável por
# permissão de ninguém.
#
# Entra por stdin o evento da ferramenta; sai 0 para deixar passar e 2 para
# barrar, com o motivo em stderr — o motivo volta para a sessão, então ele
# precisa dizer o que fazer em vez do que foi proibido.
#
# Variáveis que o motor injeta ao lançar: ORQ_STAGE, ORQ_WORKTREE, ORQ_UNIT.
set -uo pipefail

ESTAGIO="${ORQ_STAGE:-}"
WORKTREE="${ORQ_WORKTREE:-}"
CREDENCIAIS="$HOME/.config/orquestrador"

payload="$(cat 2>/dev/null || true)"
# Um ou dois níveis. O segundo argumento é opcional — sob `set -u`, referenciar
# $2 sem valor aborta a função e a cerca vira decoração que deixa tudo passar.
campo() {
  local chave="$1" sub="${2:-}"
  printf '%s' "$payload" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
v=d.get('$chave')
if isinstance(v, dict):
    v = v.get('$sub', '') if '$sub' else ''
print(str(v or ''))
" 2>/dev/null
}

FERRAMENTA="$(campo tool_name)"
CMD="$(campo tool_input command)"
CAMINHO="$(campo tool_input file_path)"

barrar() {
  printf 'A CERCA BARROU ISTO.\n\n%s\n' "$1" >&2
  exit 2
}

# ── escrita em arquivo, por qualquer ferramenta de edição ────────────────────
if [ -n "$CAMINHO" ]; then
  case "$CAMINHO" in
    "$CREDENCIAIS"/*|"$HOME"/.claude.json|"$HOME"/.ssh/*|"$HOME"/.aws/*)
      barrar "Esse arquivo guarda credencial ou a confiança de pastas da máquina.
Nenhuma sessão escreve nele. Se você precisa de uma credencial, ela já deve
estar no ambiente fechado do projeto — nunca a de uma pessoa de verdade." ;;
  esac
fi

[ "$FERRAMENTA" = "Bash" ] || exit 0
[ -n "$CMD" ] || exit 0

tem() { printf '%s' "$CMD" | grep -qE "$1"; }

# ── publicar ─────────────────────────────────────────────────────────────────
if tem '(^|[;&|`(]|[[:space:]])git[[:space:]]+push'; then
  if tem '(--force|[[:space:]]-f([[:space:]]|$)|--mirror|--delete|:[[:space:]]*$)'; then
    barrar "Publicação com força, espelho ou remoção de branch nunca é da sessão.
Se o histórico precisa ser reescrito, isso é decisão de uma pessoa: pare com
'orq hold' e escreva exatamente o que precisa ser reescrito e por quê."
  fi
  if [ "$ESTAGIO" != "integrate" ]; then
    barrar "Publicar é do estágio de INTEGRAÇÃO, e você não está nele (estágio: ${ESTAGIO:-desconhecido}).
Commite na sua cópia de trabalho e pare por aí. Quem integra e publica é a
sessão de integração, um estágio adiante nesta mesma esteira."
  fi
fi

# ── fundir e liberar versão ──────────────────────────────────────────────────
if tem '(^|[;&|`(]|[[:space:]])gh[[:space:]]+(pr[[:space:]]+merge|release)' \
   && [ "$ESTAGIO" != "integrate" ]; then
  barrar "Fundir pull request e publicar versão são do estágio de INTEGRAÇÃO.
Você está em '${ESTAGIO:-desconhecido}'. Termine o seu trabalho e deixe a
unidade andar: 'orq advance'."
fi

# ── privilégio e publicação de pacote ────────────────────────────────────────
tem '(^|[;&|`(]|[[:space:]])sudo([[:space:]]|$)' && barrar \
"Nenhuma sessão eleva privilégio. Se a tarefa exige isso, ela exige uma pessoa:
pare com 'orq hold' e escreva o que precisa ser feito como administrador."

tem '(npm|pnpm|yarn)[[:space:]]+publish' && barrar \
"Publicar pacote é irreversível e não é trabalho de sessão. Pare com 'orq hold'."

tem 'curl[^|]*\|[[:space:]]*(ba)?sh' && barrar \
"Baixar e executar script direto da rede não passa. Se a ferramenta é
necessária, declare-a no preparo do projeto, onde alguém pode revisar."

# ── apagar fora da própria cópia de trabalho ─────────────────────────────────
if tem 'rm[[:space:]]+(-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+)+'; then
  for alvo in $(printf '%s' "$CMD" | grep -oE '(^|[[:space:]])(/|~)[^[:space:]"'"'"';|&]*' | tr -d ' '); do
    caso_ok=0
    [ -n "$WORKTREE" ] && case "$alvo" in "$WORKTREE"|"$WORKTREE"/*) caso_ok=1 ;; esac
    case "$alvo" in /tmp/*|/var/folders/*|/private/tmp/*) caso_ok=1 ;; esac
    [ "$caso_ok" = 1 ] || barrar \
"Apagar recursivamente '$alvo', que está fora da sua cópia de trabalho.
Sua cópia é: ${WORKTREE:-(não informada)}. Fora dela você não apaga nada."
  done
fi

# ── mexer na própria ferramenta ──────────────────────────────────────────────
# Tanto o caminho absoluto quanto a forma com til: `cat ~/.config/orquestrador/...`
# nunca casaria com $HOME expandido.
tem "($CREDENCIAIS|~/\.config/orquestrador)" && barrar \
"Esse diretório guarda a credencial pessoal do dono da esteira. Nenhuma sessão
lê nem escreve nele. A credencial que você pode usar é a do ambiente fechado do
projeto, criada para ser descartável."

exit 0
