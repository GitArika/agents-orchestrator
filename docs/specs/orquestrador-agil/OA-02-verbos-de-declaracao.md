# OA-02 — Verbos de declaração e configuração

**Prioridade:** P0 · **Depende de:** OA-01 · **Bloqueia:** OA-03, OA-12, OA-14

## Por que existe

Com o `pipeline.toml` eliminado, o orquestrador perde o único lugar onde a esteira era
declarada. A sessão de planejamento — você conduzindo o Claude a criar os cartões e
declarar as unidades — ficou **fora desta entrega** como skill, mas ela precisa de comandos
para escrever no banco. Sem estes verbos, o banco de OA-01 nasce vazio e nada o preenche.

## Escopo

**Dentro:** `orq init`, `orq task`, `orq dep`, `orq config`, `orq export`, `orq validate`.

**Fora:** a skill de planejamento e qualquer assistente interativo (decisão de 21/09/2026);
leitura do ClickUp para popular unidades — o orquestrador não fala mais com o ClickUp
(OA-04), então `clickup_id` e `titulo` chegam por argumento, escritos por quem planeja.
**`orq gate` não existe** — decisão de 22/09/2026: o orquestrador deixa de se preocupar com
portões. Ver "Gates saem do orquestrador" abaixo.

## Desenho

**Resolução do banco, por ora: `--db` obrigatório em todo verbo.** Decisão de
22/09/2026 — nada de `$ORQ_DB` nem de "último usado" ainda; isso é conveniência que
entra quando os comandos de LEITURA (`board`, `next`, `status` — OA-03) também
precisarem resolver o banco, e faz mais sentido desenhar a resolução completa junto
deles. `--db` é uma flag do `orq` de nível superior, igual `--pipeline` já é hoje —
por isso aparece ANTES do verbo:

```bash
orq --db ~/.config/orquestrador/esteiras/front-end.db init \
    --nome "front-end" --repo ~/projetos/app --base main \
    --worktrees ~/worktrees/front-end --lista 901... --github org/app
# cria o banco, grava a config, falha se o banco já existir (--forcar recria)
# SUBSTITUI o `orq init` de hoje (que gera pipeline.toml) — mesmo nome, papel novo.

orq --db <caminho> task add  FE-01 --clickup 868abc --titulo "Uma frase em português comum" \
                   [--prioridade alta] [--modo hands-on]
orq --db <caminho> task rm   FE-01 --forcar
orq --db <caminho> task set  FE-01 --titulo "..." | --prioridade normal | --modo autonomous

orq --db <caminho> dep add   FE-03 --precisa FE-01 --precisa FE-02
orq --db <caminho> dep rm    FE-03 --precisa FE-01

orq --db <caminho> config set max_concurrent 4
orq --db <caminho> config list
orq --db <caminho> config get interval_seconds

orq --db <caminho> export [--formato toml|json]     # o estado inteiro em texto estável
orq --db <caminho> validate                          # recusa esteira incoerente, sem escrever nada
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
- **`orq task rm` é sempre destrutivo e sempre pede `--forcar`** — não há remoção "de
  leve". E `--forcar` **não** passa por cima de uma unidade em `em_progresso` ou
  `revisao`: isso significaria apagar a declaração debaixo de uma sessão viva ou de um PR
  aberto, e nenhuma bandeira destrava isso. Resolva com `orq hold`/`orq release` antes.

### Gates saem do orquestrador

Decisão de 22/09/2026: setup, verify e teardown deixam de ser configuração da esteira.
Quem executa portões de qualidade é o agente auto-contido, seguindo as regras que o
**próprio projeto** já declara no seu `CLAUDE.md` (ou `AGENTS.md`) — o mesmo arquivo que
qualquer sessão do Claude Code lê para saber como instalar dependências, rodar testes e
tipar. Duplicar isso em `pipeline.toml`/no banco produzia exatamente o risco que o
aprendizado nº 20 documenta: o comando declarado e o comando real do projeto divergindo, e
o portão falhando pelo motivo errado.

Efeito nesta unidade: **não existe `orq gate`**, e a tabela `portao` que OA-01 havia criado
sai do esquema — não há nada para declarar. Teardown de ambiente (encerrar o que a sessão
subiu) continua existindo, mas vira um comando **fixo** do orquestrador, não declarado por
esteira: ver OA-08.

### `orq validate` — o que ele recusa

Roda sozinho e também é chamado por `orq doctor` (OA-12) e antes do primeiro despacho:

1. `repo` existe e tem `.git`; `base_branch` existe; `worktree_root` está **fora** do repo;
2. nenhum ciclo de dependência; nenhuma dependência apontando para unidade inexistente;
3. toda unidade tem `clickup_id` e `titulo` não vazios;
4. o repositório declara um `CLAUDE.md` ou `AGENTS.md` na raiz — sem isso o agente não
   tem de onde tirar os portões, e a recusa é melhor que descobrir isso na primeira sessão;
5. `github_repo` preenchido (o vigia de PR de OA-08 depende dele);
6. `max_concurrent ≥ 1`, `ram_per_session_gb > 0`, `interval_seconds ≥ 30`.

### `orq export` — o que devolve a revisão perdida

Emite o estado inteiro (config, unidades, dependências) em texto ordenado de forma
estável — mesma entrada, mesmo byte. Serve para três coisas: guardar num repositório de
esteiras se o time quiser revisão, comparar duas máquinas com `diff`, e dar ao humano uma
leitura do grafo sem abrir o banco. **Não é lido de volta** — não existe `orq import`; o
banco é a autoridade, e um caminho de volta reintroduziria o arquivo que estamos eliminando.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Declarar uma esteira inteira sem editar arquivo | Roteiro de teste: `init` + 3 `task add` + 2 `dep add`; `orq board` mostra as três unidades |
| Idempotência | `orq task add FE-01 ...` duas vezes → uma unidade, saída "já declarada, sem mudança" |
| Ciclo recusado com caminho | `dep add` que fecha ciclo → saída contém `FE-03 → FE-01 → FE-03`, banco inalterado |
| Declaração deixa rastro | `SELECT tipo FROM evento WHERE tipo='declaracao'` tem uma linha por verbo executado |
| `validate` pega esteira incompleta | Banco sem `github_repo` → `orq validate` sai != 0 nomeando o campo |
| `validate` exige CLAUDE.md/AGENTS.md | Repositório sem nenhum dos dois na raiz → `orq validate` sai != 0 dizendo onde faltou |
| `export` é estável | `orq export > a; orq export > b; diff a b` vazio |
| Não existe verbo de gate | `orq gate` → erro de comando desconhecido |

## Riscos

- **Declarar trinta unidades vira trinta invocações.** É o preço de não ter arquivo. Se
  isso doer na prática, a saída é a skill de planejamento (fora desta entrega) gerando o
  lote, não um formato de importação.
- **Erro de digitação em `clickup_id` só aparece quando o agente for ler o cartão.** O
  orquestrador não valida o id contra a API porque não fala mais com o ClickUp. O agente
  descobre e trava (`orq hold`); o `motivo` diz o que houve.
- **`CLAUDE.md` incompleto ou desatualizado agora é o único portão real.** Antes, um portão
  declarado errado no TOML falhava alto e na hora — era ruim, mas visível. Um `CLAUDE.md`
  que esquece de mencionar `pnpm typecheck` faz o agente simplesmente não rodar o comando,
  e o defeito só aparece no PR. A mitigação não é desta unidade: é o `CLAUDE.md` do projeto
  ser tratado como o portão que ele passou a ser, e revisado como tal.
