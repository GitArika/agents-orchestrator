# OA-08 — O vigia de PR dentro do laço

**Prioridade:** P0 · **Depende de:** OA-03, OA-05 · **Bloqueia:** OA-09, OA-11, OA-13

## Por que existe

`revisao → pronto` é a única transição que nenhuma sessão pode fazer: quando o humano funde
o PR, a sessão daquela unidade já morreu. Alguém precisa perguntar ao GitHub, e o requisito
define a cadência: **a cada 1 minuto**, pelo `gh`.

## Escopo

**Dentro:** a consulta ao `gh`, a cadência, as transições que ela dispara, o encerramento da
worktree em `pronto`, e o comportamento quando o `gh` falha.

**Fora:** o relançamento do agente com os comentários da revisão (OA-09), o aviso no
Telegram (OA-11).

## Desenho

### Onde roda

Dentro do laço, decidido em 21/09/2026. `interval_seconds` passa a ter **60** como padrão
(era 90) e cada ciclo faz, nesta ordem: vigiar PRs → recolher sessões mortas → preencher
vaga. O vigia vem primeiro de propósito: um merge detectado neste ciclo libera dependências
que podem ser despachadas **já**, em vez de esperar o ciclo seguinte. É o mesmo raciocínio
que hoje refaz o quadro depois de um desbloqueio automático
([bin/orq:2264](../../../bin/orq:2264)).

Uma peça só para subir, parar e diagnosticar — e a consequência conhecida: **laço parado,
vigia parado**. Por isso a condição de parada por ociosidade passa a considerar unidade em
`revisao` como trabalho vivo (ver Riscos).

### A consulta

Uma chamada por unidade em `revisao`:

```bash
gh pr view <numero> --repo <github_repo> \
   --json state,mergedAt,mergeCommit,reviewDecision,isDraft,updatedAt
```

Lote pequeno por natureza — quantas unidades cabem em revisão ao mesmo tempo é da ordem de
dezenas, e o limite autenticado do GitHub é 5.000 pedidos por hora. Sem paginação, sem
webhook: webhook exigiria endereço acessível de fora, que a VPS e o Mac não têm igualmente.

### O que cada resposta dispara

| Resposta do `gh` | Transição | Efeito colateral |
| --- | --- | --- |
| `state=MERGED` | `revisao → pronto` | roda o encerramento fixo de ambiente, arquiva artefatos, remove a worktree, escreve "pronto" no cartão (OA-07), libera dependentes |
| `reviewDecision=CHANGES_REQUESTED` | `revisao → em_progresso` | relança o agente com os comentários (OA-09) |
| `state=CLOSED` e não fundido | `revisao → bloqueado` | motivo: "PR fechado sem merge"; avisa (OA-11) |
| `state=OPEN`, nada novo | nenhuma | nada |
| erro do `gh` | nenhuma | registra evento `vigia_falhou`; **não** muda status |

**Erro do `gh` nunca move unidade.** Rede instável não pode bloquear trabalho revisado, e um
`gh` desautenticado não pode transformar a esteira inteira em `bloqueado`. Três falhas
seguidas na mesma unidade geram um aviso, não uma transição.

### O que acontece em `pronto`

Decisão de 22/09/2026: **gates deixam de ser configuração da esteira** (OA-02) — `setup` e
`verify` viram trabalho do agente seguindo o `CLAUDE.md` do projeto (OA-05). Teardown é
diferente por natureza: quando o vigia detecta o merge, o agente já morreu há tempo — não
há sessão viva para ler `CLAUDE.md` nenhum. É por isso que teardown continua sendo
obrigação do orquestrador, mas vira um **comando fixo**, o mesmo para toda esteira, em vez
de configuração declarada por projeto:

1. **encerramento fixo**: para cada `docker-compose*.{yml,yaml}` ou `compose*.{yml,yaml}`
   encontrado na raiz da worktree (a mesma busca que a skill `esteira-sandbox` já usa para
   descobrir serviços), roda `docker compose -f <arquivo> down --volumes --remove-orphans`.
   Nenhum arquivo encontrado não é falha — é "nada para encerrar". Existe porque 27
   ambientes sobreviveram a uma noite segurando 8,8 GB, e continua sendo obrigatório
   independente de qualquer coisa que o `CLAUDE.md` diga — o `CLAUDE.md` é do PROJETO, e o
   projeto não tem por que saber que está rodando dentro de uma worktree descartável;
2. artefatos vão para `archive/<esteira>/<unidade>-<ts>/` com `meta.json`, como hoje
   ([bin/orq:1326](../../../bin/orq:1326));
3. a worktree é removida (`git worktree remove`), o branch **local** apagado, o **remoto
   fica** — quem remove branch fundido é o ajuste do repositório ou uma pessoa;
4. se o `docker compose down` falhar, a worktree **não** é removida e o evento
   `teardown_falhou` fica registrado para `orq sweep` cobrar.

### `orq advance --forcar`

Para o caso de merge feito fora do fluxo (squash local, merge na mão), existe a saída
manual, que grava evento dizendo que a transição foi humana. Sem ela, uma unidade fundida
por fora ficaria em `revisao` para sempre e travaria a cadeia.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Merge vira `pronto` em ≤ 1 ciclo | Teste de integração com repositório de mentira: fundir o PR, rodar um tick → status `pronto` |
| `pronto` libera dependente no MESMO ciclo | Unidade B depende de A; fundir o PR de A → no mesmo tick, B é despachada |
| Teardown roda antes de arquivar | O evento `teardown_ok` tem carimbo anterior ao arquivamento |
| Teardown falho preserva a worktree | Forçar falha no `docker compose down` → diretório continua lá, evento `teardown_falhou` gravado, `orq sweep` cobra |
| Teardown é fixo, não declarado | Worktree sem nenhum `docker-compose*.yml` → nenhum comando roda, nenhuma falha, a worktree é removida normalmente |
| Teardown encontra o compose em qualquer nome canônico | `compose.yaml`, `docker-compose.yml` e `docker-compose.override.yml` são todos encontrados e encerrados |
| `gh` fora do ar não move nada | `PATH` sem `gh` → tick registra `vigia_falhou` e nenhum status muda |
| PR fechado sem merge bloqueia | Fechar o PR → `bloqueado` com motivo legível |
| A cadência é de 1 minuto | `orq config get interval_seconds` → 60; o rastro mostra ciclos ~60s |

## Riscos

- **Laço morto, vigia morto.** Hoje o laço se encerra após 20 ciclos sem nada vivo e nada
  pronto ([bin/orq:2429](../../../bin/orq:2429)). Com o gate humano, "nada vivo" passa a ser
  comum: todas as unidades em `revisao` esperando o humano. Se a regra não mudar, o laço
  morre e ninguém percebe o merge. **Correção obrigatória nesta unidade:** unidade em
  `revisao` conta como trabalho vivo para a ociosidade. Sem isso, o gate humano mata a
  esteira em vinte minutos.
- **`gh` precisa de credencial não interativa** no host. Já é provado pelo pré-voo atual
  ([bin/orq:2769](../../../bin/orq:2769)) e continua em OA-12.
- **Draft PR.** PR aberto como rascunho não deveria contar como revisão pedida. O campo
  `isDraft` é consultado; rascunho é tratado como `OPEN` sem novidade, e o quadro mostra
  "rascunho" para a pessoa não esperar por um gate que ninguém pediu.
- **Encerramento fixo só conhece Docker Compose.** Um projeto que suba ambiente por outro
  meio (um `pnpm dev` em background, um banco instalado direto na worktree) não tem
  cobertura — o comando fixo não encontra nada para encerrar e o processo continua vivo. É
  a troca aceita ao tirar `teardown` da declaração por esteira: se isso doer na prática, o
  sinal aparece em `orq sweep`/`orq host` (RAM presa sem processo conhecido), não em
  silêncio. Convém que a skill `esteira-sandbox` continue recomendando Docker Compose como
  o padrão, já que é o único que este encerramento sabe desligar.
