# OA-05 — O papel único auto-contido

**Prioridade:** P0 · **Depende de:** OA-03, OA-04 · **Bloqueia:** OA-06, OA-07, OA-08, OA-09, OA-14

## Por que existe

Quatro papéis viram um. O agente passa a ser responsável pelo ciclo inteiro de uma unidade:
ler o requisito no ClickUp, implementar, revisar o próprio trabalho executando os portões,
abrir o PR, atualizar o cartão e devolver a unidade ao orquestrador.

O que se perde é a revisão independente — hoje quem revisa não é quem implementou, e isso
já produziu 18 reprovações em 249 sessões. O que a substitui é o **gate humano no PR**
(OA-08): a revisão deixa de ser uma sessão e passa a ser uma pessoa olhando o diff no
GitHub. É a decisão de 21/09/2026, e o desenho abaixo assume que o humano de fato revisa —
se ninguém olhar o PR, não há mais nenhuma barreira entre o agente e a base.

## Escopo

**Dentro:** o briefing único, o contrato de encerramento, a ordem das escritas, a vida da
worktree e do branch.

**Fora:** a cerca (OA-06), o texto exato dos status no ClickUp (OA-07), o retrabalho
disparado pelo PR (OA-09).

## Desenho

### O que morre

Os quatro briefings de [bin/orq:910](../../../bin/orq:910) viram um. Some `orq reject` — não
há mais revisor para reprovar; quem reprova é o humano no PR, e o caminho de volta é OA-09.
Some `--stage` de todos os comandos. Somem `ram_per_stage_gb` e `serial_stages`: com um
papel só, o orçamento é um, e a serialização da integração deixa de existir porque nenhum
agente funde.

### O briefing único

Mantém o que já provou valor e adapta o resto:

1. **Ler a tarefa inteira antes de qualquer coisa** — o bloco `CONTEXT` atual
   ([bin/orq:813](../../../bin/orq:813)) é preservado quase palavra por palavra, trocando
   `orq show` por `orq-clickup show <id>`: descrição **e** todos os comentários. É o erro
   mais caro da esteira e continua sendo.
2. **Preparo** — ler o `CLAUDE.md`/`AGENTS.md` do projeto e seguir o que ele manda para
   deixar a worktree pronta (instalar dependências, subir o que for preciso). Decisão de
   22/09/2026: **o orquestrador deixa de declarar portões.** `setup`, `verify` e `teardown`
   saem do `pipeline.toml`/banco e viram inteiramente responsabilidade do agente, seguindo
   as regras que o **próprio projeto** já documenta para qualquer sessão do Claude Code —
   não uma cópia mantida à parte, que diverge do comando real (aprendizado nº 20: o erro
   parecia do projeto e era da ferramenta, porque o comando declarado não era o comando
   verdadeiro).
3. **Implementar** com escopo fechado no cartão. Defeito fora de escopo vira comentário no
   cartão, não conserto.
4. **Revisar o próprio trabalho** — e aqui o briefing precisa ser mais duro do que era,
   porque não há segunda leitura: para cada critério de aceite, a evidência (arquivo e
   linha, ou saída de comando). Critério sem evidência **não** está atendido, e o caminho
   é travar, não afirmar.
5. **Rodar a verificação que o `CLAUDE.md` manda** (tipo, lint, teste — o que o projeto
   declarar) e colar a saída no PR. Se o `CLAUDE.md` não disser como verificar, isso não é
   "sem portão" — é um projeto sem guia, e o agente registra isso no PR em vez de inventar
   um comando.
6. **Commit e PR** — `git push -u origin <branch>` e `gh pr create`. O corpo do PR carrega:
   critérios de aceite com evidência, saída da verificação, o que ficou fora e por quê.
   **Não funde.** `gh pr merge` é barrado pela cerca (OA-06) e o briefing diz isso com
   todas as letras, porque ordem que a cerca proíbe não é ordem — o aprendizado do
   `--delete-branch` ([bin/orq:1021](../../../bin/orq:1021)) custou três sessões.
7. **Atualizar o cartão** conforme o espelho de OA-07.
8. **Encerrar** por um dos dois caminhos abaixo.

### Encerramento: dois caminhos, não três

```bash
orq advance <unidade> --pr <numero|url>   # PR aberto → 'revisao'
orq hold    <unidade> --motivo "<o que trava>"   # → 'bloqueado'
```

`--pr` é obrigatório em `advance`: sem número de PR não há o que vigiar, e a unidade ficaria
em `revisao` para sempre. O comando recusa se o PR não existir no `github_repo` declarado —
é a única chamada de rede do motor fora do vigia, e ela paga por si: pega erro de digitação
no momento em que ele acontece.

O terceiro caminho de hoje (`reject`) desaparece. O quarto — encerrar sem nenhum — continua
sendo lido como sessão morta e recolhido por OA-03.

### Ordem das escritas, e por que ela é essa

**Banco primeiro, cartão depois.** O banco é a autoridade; o cartão é o espelho que a
pessoa lê. Se o agente morrer no meio, a divergência fica visível no lugar onde alguém
olha, e o rastro do banco permite recompor. A ordem inversa deixaria o cartão dizendo
"revisão" com a esteira achando que ninguém trabalhou.

### Worktree e branch

A worktree **sobrevive** à transição para `revisao`: o humano pode pedir mudanças e o agente
é relançado nela (OA-09). Ela só é encerrada quando a unidade chega a `pronto` ou
`bloqueado` — aí o orquestrador roda o encerramento de ambiente fixo (não mais um portão
declarado; ver OA-08), arquiva os artefatos e a worktree é removida. O branch remoto fica,
como hoje, e quem o remove é o ajuste do repositório ou uma pessoa.

A worktree continua nascendo de `origin/<base>` com `fetch` antes
([bin/orq:1167](../../../bin/orq:1167)), e agora isso fica mais simples de raciocinar:
dependência só libera em `pronto`, e `pronto` significa fundido, então o código de que a
unidade depende **está** na base quando ela começa. O caso que custou uma sessão em
01/09/2026 (aprendizado nº 7) deixa de ser possível.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Existe um briefing só | `grep -c '"""Você é uma sessão' bin/orq` → 1 |
| O agente não consegue fundir | Teste da cerca (OA-06): `gh pr merge` barrado dentro da sessão |
| `advance` exige PR existente | `orq advance FE-01 --pr 999999` com PR inexistente → recusa, status inalterado |
| Sessão que encerra sem caminho é recolhida | Matar a sessão em `em_progresso` → volta a `backlog` com strike |
| A worktree sobrevive à revisão | Após `advance`, o diretório da worktree ainda existe e o branch está publicado |
| A worktree morre em `pronto` | Vigia detecta merge → `teardown` rodou, artefatos arquivados, diretório removido |
| Ordem das escritas | Rastro: o evento no banco tem carimbo anterior ao comentário no cartão |

## Riscos

- **Auto-revisão é mais fraca que revisão independente.** É a troca aceita. Mitigação
  parcial: o briefing exige evidência por critério e proíbe declarar atendido sem prova, e
  o corpo do PR passa a ser o artefato que o humano lê. Se a taxa de PR devolvido subir
  muito, a resposta é voltar com um segundo agente revisor — não afrouxar o gate humano.
- **O humano vira o gargalo.** Com dependência liberando só no merge, um PR esquecido
  trava toda a cadeia abaixo dele. Por isso o Telegram avisa PR aberto (OA-11) e o quadro
  mostra há quanto tempo a unidade está em `revisao`.
