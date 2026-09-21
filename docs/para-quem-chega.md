# Para quem chega num projeto que já usa isto

Você entrou num time onde parte das tarefas é executada por sessões de IA governadas. Este
documento é para você entender o que está acontecendo e o que se espera de você.

## O que é uma sessão

Uma sessão é uma execução de IA com **uma tarefa só**. Ela recebe a descrição do cartão como
ordem de serviço, trabalha, e termina. Não é um assistente rodando o dia inteiro: é um turno
com começo, meio e fim.

## O que é uma cópia de trabalho

Cada tarefa ganha uma cópia isolada do repositório, num branch próprio. Duas sessões nunca
mexem nos mesmos arquivos ao mesmo tempo, porque cada uma está no seu próprio diretório.

Elas ficam **fora** da pasta do projeto, de propósito — dentro, o `git status` do projeto
passaria a listar milhares de arquivos que não são seus.

## O que é uma ordem de serviço

O texto que a sessão recebe ao nascer: o objetivo único, como preparar o ambiente, o que
precisa passar antes de concluir, e o que ela **não** deve fazer. É gerado a partir do
cartão e do arquivo da esteira.

Você pode ver o que uma sessão receberia, sem lançar nada:

```bash
orq brief <tarefa>
```

Vale a pena olhar uma vez. Entender o que a sessão lê explica quase tudo sobre o que ela faz.

## As quatro etapas

Uma tarefa atravessa quatro etapas, e cada uma é uma sessão diferente:

**Especificação** — transforma o pedido numa descrição executável.
**Implementação** — escreve o código.
**Revisão** — confere, e reprova se for o caso.
**Integração** — funde e publica. É a única etapa que publica.

Onde uma etapa termina é onde a próxima começa. Nada precisa ser empurrado à mão.

## O que se espera de você

**Escrever bons cartões.** A descrição do cartão vira a ordem de serviço. Descrição vaga
vira trabalho vago — e você só descobre na revisão.

**Responder quando a esteira te chamar.** Quando uma tarefa vai para **parado**, ela está
esperando uma pessoa. O motivo está no comentário. Enquanto ninguém responde, aquela tarefa
e tudo que depende dela ficam parados.

**Revisar antes de aprovar.** A sessão de revisão confere o que dá para conferir com
ferramenta. O julgamento de produto continua sendo humano.

**Fechar o cartão.** A esteira nunca fecha por conta própria.

## Como conferir o que uma sessão fez

```bash
orq show <tarefa>          # a descrição e todos os comentários, em ordem
orq log <tarefa>           # o que a sessão fez, passo a passo
git log --oneline <branch da tarefa>
```

Cada sessão comenta no cartão o que fez e o resultado dos portões de qualidade. Se um
comentário não explica o suficiente, isso é um defeito e vale dizer.

## O que a sessão não pode fazer

Existe uma cerca. Ela barra, antes de acontecer: publicar ou fundir fora da etapa de
integração, publicar com força, elevar privilégio, publicar pacote, baixar e executar script
da internet, apagar coisas fora da própria cópia de trabalho, e ler credencial de gente de
verdade.

Se você vir uma sessão dizendo que foi barrada, foi isso — e o comportamento certo dela é
parar e explicar, nunca contornar.

## Uma coisa que costuma assustar no começo

As sessões rodam com permissão automática: elas executam sem pedir a cada passo. Isso é o que
permite a esteira andar sozinha. O que as contém é a combinação de três coisas: a cópia
isolada, a cerca, e o fato de que **elas não decidem nada de produto** — quem declara
tarefa, aprova entrega e fecha cartão é gente.

Se algo parecer errado, você pode parar tudo:

```bash
orq loop-stop            # para de despachar
orq stop <tarefa>        # encerra uma sessão específica
```
