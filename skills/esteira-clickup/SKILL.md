---
name: esteira-clickup
description: Use para ler ou escrever no ClickUp pela linha de comando e para organizar uma lista no padrão da esteira — criar os dez status canônicos, conferir se batem, ler a descrição completa e os comentários de uma tarefa, comentar, mudar status, criar tarefa, ler e definir dependências, apontar hora. Use SEMPRE que for escrever qualquer coisa no ClickUp: a escrita por outros caminhos já publicou uma aprovação assinada por outra pessoa.
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

**Fechar cartão é decisão humana.** Nunca mova para o status final por conta própria.

## Os dez status da esteira

| Estágio | Fila | Em curso | Conclusão |
| --- | --- | --- | --- |
| Especificação | backlog | especificando | spec pronta |
| Implementação | spec pronta | em progresso | aguardando revisão |
| Revisão | aguardando revisão | revisando | aguardando integração |
| Integração | aguardando integração | integrando | pronto |

A conclusão de um estágio **é** a fila do seguinte — é isso que faz a esteira andar sem
ninguém empurrando.

O décimo é **parado**: para onde a unidade vai quando trava esperando uma pessoa. Sem ele,
quem abre o quadro vê "revisando" e conclui que alguém está revisando.

```bash
orq-clickup status-provisionar <listId>                    # simula
orq-clickup status-provisionar <listId> --aplicar          # cria o que falta
```

**Duas armadilhas aqui, as duas caras de descobrir:**

Uma lista costuma **herdar** os status da pasta ou do espaço. Nesse caso, criar status nela
exige ligar a substituição — e a lista deixa de acompanhar a pasta. A ferramenta avisa e
exige `--substituir`. Se a esteira vai ocupar a pasta inteira, o certo é definir os status
**na pasta**, não na lista.

E a API **aceita o PUT, responde sucesso e não aplica nada**. Por isso a ferramenta relê a
lista depois de escrever e compara. Nunca confie na resposta: confira.

## Quem manda em quê

O **ClickUp** manda no status e no conteúdo: a descrição, os comentários, o registro do que
foi decidido. O **arquivo da esteira**, versionado no repositório do projeto, manda no
grafo: quais unidades existem, o que depende de quê, quais portões, quanto de memória por
estágio.

Dependência é fato técnico e precisa ser revisada junto com o código. Campo de ferramenta de
gestão muda sozinho e ninguém vê.

Títulos de cartão são frases em português comum, para pessoas lerem. O código da unidade
vive no arquivo, não no título.

## Receitas

```bash
orq-clickup whoami                       # de quem é a autoria
orq-clickup list <listId>                # a lista e seus status
orq-clickup find-list "<trecho do nome>" # id de lista pelo nome
orq-clickup tasks <listId>               # as tarefas abertas
orq-clickup get <taskId>                 # a tarefa e a descrição inteira
orq-clickup board <listId>               # status, dependências e vínculos de uma vez
orq-clickup comment <taskId> "texto"     # comenta (markdown funciona)
orq-clickup set-status <taskId> "<status>"
orq-clickup set-desc <taskId> arquivo.md # substitui a descrição
orq-clickup deps <taskId>                # o que barra e o que é barrado
```

## Armadilhas

- **Id de lista morto.** Rotas de navegação devolvem id de lista já apagada: a leitura
  funciona e a escrita responde 404 sem explicar. Resolva pelo nome com `find-list`.
- **Apontamento de hora aceita só três campos** — `{tid, start, duration}`. Descrição e
  etiqueta são recurso pago e devolvem 403.
- **Nunca renomeie nem apague status existente.** Pode haver tarefa nele, e mexer nisso é
  decisão de quem é dono do processo.
