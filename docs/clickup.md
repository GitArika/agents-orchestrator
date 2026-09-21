# Organização no ClickUp

## Os dez status

| Etapa | A tarefa espera em | Enquanto trabalham, ela fica em | Quando termina, vai para |
| --- | --- | --- | --- |
| Especificação | backlog | especificando | spec pronta |
| Implementação | spec pronta | em progresso | aguardando revisão |
| Revisão | aguardando revisão | revisando | aguardando integração |
| Integração | aguardando integração | integrando | pronto |

Repare que **onde uma etapa termina é onde a próxima começa**. É só isso que faz a esteira
andar: ninguém precisa empurrar a tarefa de uma etapa para a outra.

O décimo status é **parado**. É para onde a tarefa vai quando trava esperando uma resposta
sua. Sem ele, quem abre o quadro vê "revisando" e acha que alguém está revisando — quando
na verdade ninguém está fazendo nada e todo mundo espera você.

## Criar os status na sua lista

```bash
orq-clickup status-provisionar <id da lista>              # mostra o que faria
orq-clickup status-provisionar <id da lista> --aplicar    # cria
```

Ele **só acrescenta**. Nunca renomeia nem apaga status que já existe — pode haver tarefa
dentro, e mexer nisso é decisão de quem é dono do processo.

**Uma coisa para saber antes:** listas costumam **herdar** os status da pasta em que estão.
Se a sua herda, criar status só nela exige ligar a substituição — e a partir daí ela deixa
de acompanhar mudanças feitas na pasta. A ferramenta avisa e pede confirmação explícita.

Se a esteira vai ocupar a pasta inteira, o mais limpo é definir os status **na pasta**.

## Quem manda em quê

Duas fontes, e elas não se sobrepõem:

**O ClickUp manda no status e no conteúdo.** Em que etapa a tarefa está, o que ela pede, o
que foi decidido nos comentários. É o quadro do time.

**O arquivo da esteira manda no desenho.** Quais tarefas a esteira conhece, o que depende de
quê, o que precisa passar antes de concluir. Esse arquivo vive no repositório do projeto e é
revisado junto com o código.

Por que não pôr as dependências no ClickUp? Porque dependência é decisão técnica, e decisão
técnica tem de ser revisada por quem entende do código. Campo de ferramenta de gestão muda
sozinho, sem revisão, e ninguém vê.

**Tarefa que está no ClickUp e não está no arquivo nunca é executada.** Ela aparece marcada
no quadro, para você notar. Isso é proposital: uma esteira que executa o que aparece na
lista é uma esteira que qualquer pessoa dispara sem querer.

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

## Como escrever os cartões

**O título é uma frase em português comum.** "A tela de frota trava sozinha e os botões
param de responder", não "FE-16". O código da tarefa vive no arquivo da esteira; o título é
para pessoas lerem no quadro.

**A descrição é a especificação.** É ela que a sessão lê como ordem de serviço. Vale o
tempo que você investir: descrição vaga vira trabalho vago.

## Apontar hora

Envie apenas o essencial: a tarefa, o começo e a duração. Descrição e etiqueta em
apontamento de hora são recurso pago, e mandá-los faz a operação inteira ser recusada com um
erro que não explica isso.

## Fechar cartão é seu

A sessão nunca move um cartão para o status final por conta própria. Ela deixa em
"aguardando integração" ou "pronto" conforme configurado, e o fechamento é decisão humana.
