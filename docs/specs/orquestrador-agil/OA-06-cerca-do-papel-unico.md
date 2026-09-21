# OA-06 — A cerca do papel único

**Prioridade:** P0 · **Depende de:** OA-05 · **Bloqueia:** OA-12

## Por que existe

A cerca de hoje decide pelo **estágio**: `git push` e `gh pr merge` só passam quando
`ORQ_STAGE=integrate` ([hooks/cerca.sh:64](../../../hooks/cerca.sh:64)). Com um papel só,
`ORQ_STAGE` deixa de existir e a condição vira sempre falsa — o agente não conseguiria
publicar o próprio branch, que agora é obrigação dele. Sem esta unidade, OA-05 não roda.

A inversão é precisa: **publicar o próprio branch passa a ser permitido; fundir passa a ser
proibido para sempre.** Antes existia uma sessão autorizada a fundir; agora não existe
nenhuma, porque o merge é o gate humano.

## Escopo

**Dentro:** reescrever as regras de publicação da cerca, trocar `ORQ_STAGE` por
`ORQ_BRANCH`/`ORQ_BASE`, e refazer a bateria de casos nos dois lados.

**Fora:** as outras travas (privilégio, publicação de pacote, script da rede, apagar fora da
worktree, credenciais) ficam como estão — nenhuma delas dependia do estágio.

## Desenho

### As variáveis injetadas mudam

| Hoje | Passa a ser |
| --- | --- |
| `ORQ_STAGE=implement\|review\|integrate` | — (removida) |
| `ORQ_WORKTREE`, `ORQ_UNIT` | iguais |
| — | `ORQ_BRANCH` — o branch desta unidade |
| — | `ORQ_BASE` — o branch de publicação |

### Regras novas

**1. `git push` passa apenas para o branch da própria unidade.**

Passa: `git push -u origin <ORQ_BRANCH>`, `git push` sem argumento quando o branch corrente
é `ORQ_BRANCH`, `git push origin HEAD`.

Barra: qualquer push cujo destino seja `ORQ_BASE`; push com `--force`, `-f`,
`--force-with-lease`, `--mirror`, `--delete` ou refspec começando por `:`; push para um
branch que não é o da unidade. A checagem do branch corrente usa
`git -C "$ORQ_WORKTREE" symbolic-ref --short HEAD`, não confia no texto do comando —
`cd /outro/lugar && git push` continua sendo a linha trivial que a cerca precisa pegar.

**2. `gh pr merge` e `git merge` no branch de publicação nunca passam.** Sem exceção e sem
variável que destrave. A mensagem tem de dizer o que fazer, porque ordem impossível já
custou três sessões: *"Fundir é do gate humano. Seu trabalho acaba no PR aberto:
`orq advance <unidade> --pr <n>`."*

**3. `gh release` continua barrado.** Nenhum papel publica versão.

**4. `gh pr create` passa** — é obrigação do papel. Mas `--base` diferente de `ORQ_BASE`
barra: PR apontado para o branch errado é trabalho perdido descoberto tarde.

**5. O banco da esteira entra na lista de arquivos intocáveis.** Ele vive em
`~/.config/orquestrador/esteiras/<nome>.db`, dentro do diretório que a cerca já protege
([hooks/cerca.sh:110](../../../hooks/cerca.sh:110)) — a regra atual já cobre por acidente, e
esta unidade a torna explícita e testada. O agente muda o estado **só** pelos verbos
(`orq advance`, `orq hold`); `sqlite3` apontado para o banco barra. Uma sessão que pode
reescrever o próprio estado não tem esteira.

## Critérios de aceite

Metade dos casos é o que precisa barrar, metade é o trabalho normal que precisa passar —
cerca que barra tudo também não serve. `testes/cerca.sh` é estendido com, no mínimo:

| Comando | Esperado |
| --- | --- |
| `git push -u origin $ORQ_BRANCH` | passa |
| `git push` (HEAD = branch da unidade) | passa |
| `cd /tmp && git push origin $ORQ_BASE` | barra |
| `git push --force origin $ORQ_BRANCH` | barra |
| `git push origin --delete $ORQ_BRANCH` | barra |
| `git push origin outro-branch` | barra |
| `gh pr create --base $ORQ_BASE --head $ORQ_BRANCH` | passa |
| `gh pr create --base producao` | barra |
| `gh pr merge --squash` | barra |
| `gh pr merge 42 --merge` | barra |
| `git merge origin/$ORQ_BASE` (trazer a base para o branch) | passa |
| `git checkout $ORQ_BASE && git merge $ORQ_BRANCH` | barra |
| `sqlite3 ~/.config/orquestrador/esteiras/x.db "update unidade …"` | barra |
| `orq advance FE-01 --pr 12` | passa |
| `pnpm test`, `pnpm install`, `git commit` | passam |

E duas provas de integridade que já existem e continuam valendo: `./testes/cerca.sh` sai 0
para instalar, e a impressão SHA da cerca é conferida pelo pré-voo
([bin/orq:1103](../../../bin/orq:1103)).

## Riscos

- **Cerca com defeito é pior do que nenhuma.** A primeira versão ficou inerte por um erro de
  leitura do evento e deixava tudo passar, sem sinal. Por isso os casos "passa" são tão
  obrigatórios quanto os "barra": uma cerca que barra tudo seria notada em minutos; uma que
  passa tudo, não.
- **`--force-with-lease` é novo na lista.** Não estava na regex de hoje
  ([hooks/cerca.sh:66](../../../hooks/cerca.sh:66)) e reescreve histórico igual. Entra com
  caso de teste próprio.
