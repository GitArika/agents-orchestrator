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
# Variáveis que o motor injeta ao lançar: ORQ_WORKTREE, ORQ_UNIT, ORQ_BRANCH,
# ORQ_BASE. `ORQ_STAGE` não existe mais (OA-04 removeu os estágios) — a regra
# de publicação de hoje é por BRANCH da própria unidade, não por papel
# (OA-06): não há mais sessão de integração nenhuma. Publicar o próprio
# branch é permitido; fundir é proibido para sempre — quem funde é uma
# pessoa, olhando o PR.
set -uo pipefail

WORKTREE="${ORQ_WORKTREE:-}"
BRANCH="${ORQ_BRANCH:-}"
BASE="${ORQ_BASE:-}"
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
      barrar "Esse arquivo guarda credencial, a confiança de pastas da máquina, ou o
banco da esteira (que fica dentro de $CREDENCIAIS/esteiras/). Nenhuma sessão
escreve nele — o estado muda SÓ pelos verbos (\`orq advance\`, \`orq hold\`).
Se você precisa de uma credencial, ela já deve estar no ambiente fechado do
projeto — nunca a de uma pessoa de verdade." ;;
  esac
fi

[ "$FERRAMENTA" = "Bash" ] || exit 0
[ -n "$CMD" ] || exit 0

tem() { printf '%s' "$CMD" | grep -qE "$1"; }

# ── publicar: só o branch da própria unidade, nunca reescrevendo histórico ──
if tem '(^|[;&|`(]|[[:space:]])git[[:space:]]+push([[:space:]]|$)'; then
  # 1. Reescrita de histórico nunca passa — nem no branch da própria unidade.
  #    `--force-with-lease` está aqui de propósito: reescreve igual, e não
  #    estava na lista antes.
  if tem '(--force([[:space:]=]|$)|--force-with-lease|[[:space:]]-f([[:space:]]|$)|--mirror|--delete)'; then
    barrar "Publicação com força, espelho ou remoção de branch nunca é da sessão —
nem no seu próprio branch. Se o histórico precisa ser reescrito, ou um
branch remoto precisa sumir, isso é decisão de uma pessoa: pare com
'orq hold' e escreva exatamente o que precisa acontecer e por quê."
  fi

  # 2. Para onde este push aponta? Resolvido por um parser de verdade
  #    (shlex), não por regex — refspec pode vir de formas diferentes
  #    (`origin BRANCH`, `origin BRANCH:BRANCH`, `origin :BRANCH` para
  #    apagar, `origin HEAD`, ou nada — o branch corrente decide).
  ATUAL=""
  if [ -n "$WORKTREE" ]; then
    ATUAL="$(git -C "$WORKTREE" symbolic-ref --short HEAD 2>/dev/null || true)"
  fi
  ALVOS="$(CMD_PUSH="$CMD" python3 -c "
import os, shlex, sys
texto = os.environ.get('CMD_PUSH', '')
try:
    partes = shlex.split(texto)
except ValueError:
    print('__INDETERMINADO__')
    sys.exit()
alvos = []
for i, tok in enumerate(partes):
    if tok != 'push' or i == 0 or partes[i - 1] != 'git':
        continue
    resto = partes[i + 1:]
    for j, t in enumerate(resto):
        if t in ('&&', '||', ';', '|'):
            resto = resto[:j]
            break
    posicionais = [p for p in resto if not p.startswith('-')]
    if len(posicionais) <= 1:
        alvos.append('__ATUAL__')
        continue
    alvo = posicionais[1]
    if alvo.startswith(':'):
        alvos.append('__APAGAR__')          # git push origin :branch — apaga
        continue
    if ':' in alvo:
        origem, _, destino = alvo.partition(':')
        alvo = destino or '__APAGAR__'      # 'origem:' também apaga
    alvos.append(alvo)
print('\n'.join(alvos) if alvos else '__ATUAL__')
")"
  if [ -z "$ALVOS" ]; then
    ALVOS="__ATUAL__"
  fi
  while IFS= read -r alvo; do
    [ -n "$alvo" ] || continue
    case "$alvo" in
      __INDETERMINADO__)
        barrar "Não consegui entender para onde este \`git push\` aponta. Publique de
um jeito direto: \`git push -u origin $BRANCH\`." ;;
      __APAGAR__)
        barrar "Apagar um branch remoto (refspec vazio) nunca é da sessão. Pare com
'orq hold' se um branch remoto precisa ser removido — isso é decisão de
uma pessoa." ;;
      __ATUAL__|HEAD)
        if [ -z "$ATUAL" ] || [ "$ATUAL" != "$BRANCH" ]; then
          barrar "Este \`git push\` publicaria o branch atual ('${ATUAL:-desconhecido}'),
que não é o seu ('${BRANCH:-desconhecido}'). Publique explicitamente:
\`git push -u origin $BRANCH\`."
        fi ;;
      "$BASE")
        barrar "Publicar em '$BASE' — o branch de publicação — nunca é da sessão.
Seu trabalho acaba no PR aberto: \`orq advance <unidade> --pr <n>\`.
Quem funde e publica em '$BASE' é uma pessoa, pelo gate humano." ;;
      "$BRANCH") ;;   # o único caso que passa
      *)
        barrar "Este \`git push\` aponta para '$alvo', que não é o seu branch
('${BRANCH:-desconhecido}'). Publique só o que é seu:
\`git push -u origin $BRANCH\`." ;;
    esac
  done <<< "$ALVOS"
fi

# ── fundir: NUNCA passa, sem exceção e sem variável que destrave ────────────
if tem '(^|[;&|`(]|[[:space:]])gh[[:space:]]+pr[[:space:]]+merge'; then
  barrar "Fundir é do gate humano. Seu trabalho acaba no PR aberto:
'orq advance <unidade> --pr <n>'. Nenhuma sessão funde, em nenhuma
circunstância — quem decide é uma pessoa, olhando o diff."
fi

# `git merge` só passa trazendo a BASE para dentro do branch da unidade
# (`git merge origin/$ORQ_BASE`, o --ff-only de sempre). Barra se o comando
# primeiro troca para o branch de publicação — `git checkout $ORQ_BASE && …` —
# ou se a worktree já está nele: fundir DENTRO da base é integração, e
# integração é gate humano agora, não um estágio desta esteira.
if tem '(^|[;&|`(]|[[:space:]])git[[:space:]]+merge([[:space:]]|$)'; then
  na_base=0
  if [ -n "$BASE" ]; then
    tem "(^|[;&|\`(]|[[:space:]])git[[:space:]]+(checkout|switch)([[:space:]]+-[a-zA-Z]+)*[[:space:]]+$BASE([[:space:]]|\$)" \
      && na_base=1
    if [ -n "$WORKTREE" ]; then
      atual_agora="$(git -C "$WORKTREE" symbolic-ref --short HEAD 2>/dev/null || true)"
      [ -n "$atual_agora" ] && [ "$atual_agora" = "$BASE" ] && na_base=1
    fi
  fi
  if [ "$na_base" = 1 ]; then
    barrar "Fundir dentro de '$BASE' é integração, e integração é do gate humano
agora — nenhuma sessão publica nem funde em '$BASE'. Se o objetivo é
trazer a base atualizada para o SEU branch, faça o inverso:
\`git merge origin/$BASE\` estando no seu próprio branch."
  fi
fi

# ── liberar versão: nenhum papel publica ────────────────────────────────────
tem '(^|[;&|`(]|[[:space:]])gh[[:space:]]+release' && barrar \
"Publicar uma versão nunca é da sessão. Pare com 'orq hold' se isso for
mesmo necessário — é decisão de uma pessoa."

# ── abrir PR: só apontando para a base declarada ─────────────────────────────
if tem '(^|[;&|`(]|[[:space:]])gh[[:space:]]+pr[[:space:]]+create'; then
  ALVO_BASE="$(CMD_PR="$CMD" python3 -c "
import os, shlex
partes = shlex.split(os.environ.get('CMD_PR', ''))
for i, t in enumerate(partes):
    if t == '--base' and i + 1 < len(partes):
        print(partes[i + 1]); break
    if t.startswith('--base='):
        print(t.split('=', 1)[1]); break
" 2>/dev/null)"
  if [ -n "$ALVO_BASE" ] && [ -n "$BASE" ] && [ "$ALVO_BASE" != "$BASE" ]; then
    barrar "Este PR apontaria para '$ALVO_BASE', mas o branch de publicação desta
esteira é '$BASE'. PR para o lugar errado é trabalho perdido descoberto
tarde — abra com: \`gh pr create --base $BASE ...\`."
  fi
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

# ── mexer na própria ferramenta (inclui o banco da esteira, dentro deste
# diretório) ──────────────────────────────────────────────────────────────
# Tanto o caminho absoluto quanto a forma com til: `cat ~/.config/orquestrador/...`
# nunca casaria com $HOME expandido.
tem "($CREDENCIAIS|~/\.config/orquestrador)" && barrar \
"Esse diretório guarda a credencial pessoal do dono da esteira e o banco da
esteira (esteiras/*.db). Nenhuma sessão lê nem escreve nele — o estado muda
SÓ pelos verbos (\`orq advance\`, \`orq hold\`). A credencial que você pode
usar é a do ambiente fechado do projeto, criada para ser descartável."

exit 0
