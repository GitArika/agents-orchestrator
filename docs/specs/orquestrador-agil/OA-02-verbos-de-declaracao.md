# OA-02 — Verbos de declaração e configuração

**Prioridade:** P0 · **Depende de:** OA-01 · **Bloqueia:** OA-03, OA-12, OA-14

## Por que existe

Com o `pipeline.toml` eliminado, o orquestrador perde o único lugar onde a esteira era
declarada. A sessão de planejamento — você conduzindo o Claude a criar os cartões e
declarar as unidades — ficou **fora desta entrega** como skill, mas ela precisa de comandos
para escrever no banco. Sem estes verbos, o banco de OA-01 nasce vazio e nada o preenche.

## Escopo

**Dentro:** `orq init`, `orq task`, `orq dep`, `orq gate`, `orq config`, `orq export`,
`orq validate`.

**Fora:** a skill de planejamento e qualquer assistente interativo (decisão de 21/09/2026);
leitura do ClickUp para popular unidades — o orquestrador não fala mais com o ClickUp
(OA-04), então `clickup_id` e `titulo` chegam por argumento, escritos por quem planeja.

## Desenho

```bash
orq init --nome "front-end" --repo ~/projetos/app --base main \
         --worktrees ~/worktrees/front-end --lista 901... --github org/app
# cria o banco, grava a config, falha se o banco já existir (--forcar recria)

orq task add  FE-01 --clickup 868abc --titulo "Uma frase em português comum" \
              [--prioridade alta] [--modo hands-on]
orq task rm   FE-01
orq task set  FE-01 --titulo "..." | --prioridade normal | --modo autonomous

orq dep add   FE-03 --precisa FE-01 --precisa FE-02
orq dep rm    FE-03 --precisa FE-01

orq gate add  setup  "pnpm install --frozen-lockfile"
orq gate add  verify "pnpm typecheck" --ordem 1
orq gate add  teardown "docker compose -f sandbox.yml down -v"
orq gate rm   <id> | orq gate list

orq config set max_concurrent 4 | orq config list | orq config get interval_seconds

orq export [--formato toml|json]     # o estado inteiro em texto estável
orq validate                          # recusa esteira incoerente, sem escrever nada
```

### Regras de escrita

- **Todo verbo escreve dentro de uma única `transacao`** de OA-01 e grava um `evento` de
  tipo `declaracao`. Declarar é mudança de estado: quem alterou uma dependência às 3h da
  manhã tem de aparecer no rastro, já que não há mais PR para mostrar.
- **`orq task add` é idempotente por `chave`**: repetir com os mesmos valores não é erro,
  repetir com valores diferentes exige `--forcar`. Uma sessão de planejamento que repete o
  comando não pode produzir duas unidades.
- **`orq dep add` valida o grafo inteiro antes de gravar.** Ciclo recusa com o caminho
  completo (`FE-03 → FE-01 → FE-03`), não com "dependência inválida".
- **`orq task rm` recusa unidade com sessão viva ou PR aberto.** `--forcar` exige que a
  unidade esteja em `backlog` ou `pronto`.

### `orq validate` — o que ele recusa

Roda sozinho e também é chamado por `orq doctor` (OA-12) e antes do primeiro despacho:

1. `repo` existe e tem `.git`; `base_branch` existe; `worktree_root` está **fora** do repo;
2. nenhum ciclo de dependência; nenhuma dependência apontando para unidade inexistente;
3. toda unidade tem `clickup_id` e `titulo` não vazios;
4. há pelo menos um portão `verify`, ou a config declara explicitamente
   `sem_portoes = true` — portão ausente por esquecimento e portão ausente por decisão
   não podem se parecer;
5. `github_repo` preenchido (o vigia de PR de OA-08 depende dele);
6. `max_concurrent ≥ 1`, `ram_per_session_gb > 0`, `interval_seconds ≥ 30`.

### `orq export` — o que devolve a revisão perdida

Emite o estado inteiro (config, unidades, dependências, portões) em texto ordenado de forma
estável — mesma entrada, mesmo byte. Serve para três coisas: guardar num repositório de
esteiras se o time quiser revisão, comparar duas máquinas com `diff`, e dar ao humano uma
leitura do grafo sem abrir o banco. **Não é lido de volta** — não existe `orq import`; o
banco é a autoridade, e um caminho de volta reintroduziria o arquivo que estamos eliminando.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Declarar uma esteira inteira sem editar arquivo | Roteiro de teste: `init` + 3 `task add` + 2 `dep add` + 2 `gate add`; `orq board` mostra as três unidades |
| Idempotência | `orq task add FE-01 ...` duas vezes → uma unidade, saída "já declarada, sem mudança" |
| Ciclo recusado com caminho | `dep add` que fecha ciclo → saída contém `FE-03 → FE-01 → FE-03`, banco inalterado |
| Declaração deixa rastro | `SELECT tipo FROM evento WHERE tipo='declaracao'` tem uma linha por verbo executado |
| `validate` pega esteira incompleta | Banco sem `github_repo` → `orq validate` sai != 0 nomeando o campo |
| `export` é estável | `orq export > a; orq export > b; diff a b` vazio |

## Riscos

- **Declarar trinta unidades vira trinta invocações.** É o preço de não ter arquivo. Se
  isso doer na prática, a saída é a skill de planejamento (fora desta entrega) gerando o
  lote, não um formato de importação.
- **Erro de digitação em `clickup_id` só aparece quando o agente for ler o cartão.** O
  orquestrador não valida o id contra a API porque não fala mais com o ClickUp. O agente
  descobre e trava (`orq hold`); o `motivo` diz o que houve.
