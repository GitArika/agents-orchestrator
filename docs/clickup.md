# Organização no ClickUp

## Os cinco status

| Status | O que significa |
| --- | --- |
| **backlog** | declarada, esperando dependência ou vaga para começar |
| **em progresso** | uma sessão está trabalhando nela agora |
| **revisão** | o PR está aberto, esperando uma pessoa |
| **bloqueado** | parou por decisão humana, ou o PR voltou o limite de vezes |
| **pronto** | o PR foi fundido — estado terminal |

São os mesmos cinco do banco SQLite (`backlog`, `em_progresso`, `revisao`, `bloqueado`,
`pronto`) — este é o espelho que o time lê no quadro do ClickUp. Um agente nunca escreve o
status pensando nele mesmo: escreve pensando em quem abrir o cartão sem saber nada do
orquestrador.

## Criar os status na sua lista

```bash
orq-clickup padronizar <id da lista> --cinco              # mostra o que faria
orq-clickup padronizar <id da lista> --cinco --aplicar    # substitui
```

Diferente do antigo `status-provisionar` (que só acrescentava, para o modelo de dez status),
`padronizar --cinco` **substitui a lista inteira** pelos cinco de cima — nem um a mais. Ele
recusa aplicar se houver tarefa num status que não é nenhum dos cinco: mova-a antes.

**Uma coisa para saber antes:** listas costumam **herdar** os status da pasta em que estão.
Se a sua herda, criar status só nela exige ligar a substituição — e a partir daí ela deixa
de acompanhar mudanças feitas na pasta. A ferramenta avisa e pede confirmação explícita.

Se a esteira vai ocupar a pasta inteira, o mais limpo é definir os status **na pasta**.

## Quem manda em quê

Duas fontes, e elas não se sobrepõem:

**O ClickUp manda no conteúdo.** O que a tarefa pede, o que foi decidido nos comentários, o
histórico de idas e vindas de uma revisão. É o quadro do time.

**O banco da esteira manda no status e no grafo.** Em que status a unidade está de verdade,
o que depende de quê, o PR aberto, quantas devoluções já teve. O ClickUp só **espelha** o
status — nunca é ele quem decide a transição.

**A escrita no ClickUp é sempre do AGENTE, nunca do motor.** `bin/orq` não fala com a API do
ClickUp em nenhum momento: quem lê e escreve o cartão é a própria sessão, através de
`orq-clickup`, seguindo os passos do seu briefing. Se o cartão e o banco divergirem — a
escrita falhou no meio, por exemplo — o banco é a autoridade; o cartão é só o que uma pessoa
lê primeiro.

**Tarefa que está no ClickUp e não foi declarada (`orq task add`) nunca é executada.** Isso é
proposital: uma esteira que executa o que aparece na lista é uma esteira que qualquer pessoa
dispara sem querer.

## Escrever no ClickUp

Toda escrita sai por:

```bash
orq-clickup comment <tarefa> "texto"
orq-clickup set-status <tarefa> "<status>"
```

**Antes de escrever, confira de quem é a autoria:**

```bash
orq-clickup whoami
```

Isto não é preciosismo. Em agosto de 2026, um registro de aprovação foi publicado num
cartão **assinado por outra pessoa** — porque a escrita saiu por um caminho autenticado com
a sessão de outra pessoa na mesma máquina. Aprovação atribuída a quem não aprovou é
falsificação de registro, mesmo sem ninguém ter tido má intenção.

## Ler a ordem de serviço inteira

```bash
orq-clickup show <tarefa>
```

Descrição **e** todos os comentários, do mais antigo ao mais recente — é o primeiro comando
de toda sessão. Os comentários não são conversa paralela: é onde mora divergência registrada
por quem veio antes, ambiguidade deixada em aberto de propósito, ou o pedido de mudança de
uma revisão devolvida. Tratar só a descrição como a tarefa inteira já foi o erro mais caro
desta esteira.

## Como escrever os cartões

**O título é uma frase em português comum.** "A tela de frota trava sozinha e os botões
param de responder", não "FE-16". O código da unidade vive no banco da esteira; o título é
para pessoas lerem no quadro.

**A descrição é a especificação.** É ela que a sessão lê como ordem de serviço. Vale o
tempo que você investir: descrição vaga vira trabalho vago.

## Apontar hora

```bash
orq-clickup time-entry <tarefa> <início ISO> <minutos>
```

Envie apenas o essencial: a tarefa, o começo e a duração. Descrição e etiqueta em
apontamento de hora são recurso pago, e mandá-los faz a operação inteira ser recusada com um
erro que não explica isso.

## Fundir e fechar é seu

A sessão nunca funde o PR, e nunca move o cartão para `pronto` por conta própria — a cerca
barra `gh pr merge` sem exceção. Fechar é decisão humana; o vigia só marca `pronto` **depois**
de ver o merge de verdade no GitHub.
