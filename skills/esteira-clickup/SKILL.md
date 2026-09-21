---
name: esteira-clickup
description: Use para ler ou escrever no ClickUp pela linha de comando e para organizar uma lista no padrão da esteira — criar os cinco status canônicos, conferir se batem, ler a descrição completa e os comentários de uma tarefa, comentar, mudar status, criar tarefa, ler e definir dependências, apontar hora. Use SEMPRE que for escrever qualquer coisa no ClickUp: a escrita por outros caminhos já publicou uma aprovação assinada por outra pessoa.
---

# ClickUp pela linha de comando

## A regra de escrita, antes de tudo

**Toda escrita sai por `orq-clickup`**, que lê o token pessoal de
`~/.config/orquestrador/credenciais.env`. E **antes de escrever, confirme a autoria**:

```bash
orq-clickup whoami
```

Em 27/08/2026 um registro de aprovação foi publicado num cartão **assinado por outra
pessoa**, porque a escrita saiu por um servidor de integração cuja sessão autorizada na
máquina não era a do dono do projeto. Aprovação atribuída a quem não aprovou é falsificação
de registro, ainda que involuntária.

Servidor de integração é aceitável para **leitura**, mas a linha de comando é melhor mesmo
aí: aquele caminho trunca descrição, omite valor de campo personalizado, perde a formatação
do comentário (título e negrito somem) e gasta cerca de 700 tokens por resposta.

**Fundir e fechar cartão são decisão humana.** Nenhuma sessão move para `pronto` por conta
própria, e nenhuma funde o PR — a cerca barra `gh pr merge`, sem exceção.

## Os cinco status da esteira

| Status | Significa |
| --- | --- |
| backlog | esperando dependência ou vaga |
| em progresso | uma sessão está trabalhando agora |
| revisão | PR aberto, esperando uma pessoa |
| bloqueado | parou por decisão humana, ou PR devolvido até o limite |
| pronto | PR fundido — terminal |

Os mesmos cinco do `CHECK` da tabela `unidade` no banco SQLite — o ClickUp só espelha.

```bash
orq-clickup padronizar <listId|alias> --cinco              # simula
orq-clickup padronizar <listId|alias> --cinco --aplicar    # substitui pelos cinco
```

Diferente do `status-provisionar` antigo (que só acrescentava, para o modelo de dez
status), `padronizar --cinco` **substitui a lista inteira**. Ele recusa se houver tarefa num
status que não é um dos cinco — mova-a antes de aplicar.

**Duas armadilhas aqui, as duas caras de descobrir:**

Uma lista costuma **herdar** os status da pasta ou do espaço. Nesse caso, aplicar exige
`--substituir` — e a lista deixa de acompanhar a pasta. Se a esteira vai ocupar a pasta
inteira, o certo é definir os status **na pasta**, não na lista.

E a API **aceita o PUT, responde sucesso e não aplica nada**. Por isso a ferramenta relê a
lista depois de escrever e compara. Nunca confie na resposta: confira.

## Quem manda em quê

O **ClickUp** manda no conteúdo: a descrição, os comentários, o histórico de idas e vindas
de uma revisão. O **banco da esteira** manda no status de verdade e no grafo: quais unidades
existem, o que depende de quê, PR aberto, devoluções. O status no ClickUp é sempre um
espelho, nunca a fonte da transição.

Dependência é fato técnico e precisa ser revisada junto com o código — por isso mora no
banco, declarada com `orq dep add`, não num campo do ClickUp que muda sozinho e ninguém vê.

Títulos de cartão são frases em português comum, para pessoas lerem. O código da unidade
(`FE-01`) vive no banco, não no título.

## Receitas

```bash
orq-clickup whoami                       # de quem é a autoria
orq-clickup list <listId>                # a lista e seus status
orq-clickup find-list "<trecho do nome>" # id de lista pelo nome
orq-clickup tasks <listId>               # as tarefas abertas
orq-clickup show <taskId>                # descrição inteira + todos os comentários, em ordem
orq-clickup get <taskId>                 # status/tags/links, resumido
orq-clickup board <listId>               # status, dependências e vínculos de uma vez
orq-clickup comment <taskId> "texto"     # comenta (markdown funciona)
orq-clickup set-status <taskId> "<status>"
orq-clickup set-desc <taskId> arquivo.md # substitui a descrição
orq-clickup deps <taskId>                # o que barra e o que é barrado
orq-clickup time-entry <taskId> <início ISO> <minutos>
```

## Armadilhas

- **Id de lista morto.** Rotas de navegação devolvem id de lista já apagada: a leitura
  funciona e a escrita responde 404 sem explicar. Resolva pelo nome com `find-list`.
- **Apontamento de hora aceita só três campos** — `{tid, start, duration}`. Descrição e
  etiqueta são recurso pago e devolvem 403.
- **Nunca renomeie nem apague status existente à mão.** Pode haver tarefa nele, e mexer
  nisso é decisão de quem é dono do processo — é por isso que `padronizar` recusa órfã em
  vez de mover sozinho.
