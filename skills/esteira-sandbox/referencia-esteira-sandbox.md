# Referência: o ambiente fechado

Uma implementação real, para ler antes de construir a sua. **Não copie**: o produto é
outro. Copie as decisões, não os serviços.

## O que subia

Mongo, Postgres e um coletor de e-mail, em Docker, publicados em `127.0.0.1` e **nunca** em
`0.0.0.0`, em portas próprias, longe das de desenvolvimento — porque colidir com elas faria
a sessão escrever no banco de verdade achando que estava no ambiente fechado.

## Como o back acabava no ambiente fechado sem editar nada no repositório

O comando de desenvolvimento do back carregava um `.env` e o carregador de configuração só
preenchia o que **ainda não existia** no ambiente. Então variável exportada vencia o arquivo
do repositório. O subidor exportava a conexão dos bancos, os segredos de token, a origem
aceita e a porta — e o `.env` que apontava para homologação ficava intocado no disco,
perdendo por precedência.

Isso é melhor do que editar o arquivo: não há nada para desfazer, e ninguém commita por
engano um arquivo alterado.

## A saída vai para arquivo

Soltar os servidores com a saída num cano mata o filho no primeiro `write` depois que o pai
sai: o cano fecha e o processo leva EPIPE. Foi assim que o front morreu e o back sobreviveu
numa mesma execução — a diferença era só quem escreveu primeiro. Arquivo resolve, e ainda
dá o log depois.

## O vazamento de 01/09/2026, com os números

O registro da aplicação no ar era **um arquivo só**. Cada subida sobrescrevia o da anterior,
cujos processos continuavam vivos sem ninguém que soubesse o número deles. E o comando de
derrubar só derrubava os containers.

Resultado, medido em 02/09/2026:

- **27 pilhas** de back+front, **147 processos**, **8,8 GB** de memória real presa
- a fatia da esteira em **12,7 GB de 18**, com o **swap dela 100% cheio**
- **1.104.943 freadas** por excesso de memória, acumuladas
- e o medidor da máquina mostrando **16 GB livres** — por isso ninguém percebeu

Uma única cópia de trabalho tinha acumulado nove pilhas.

Depois da limpeza: 4,9 GB e swap zerado.

## O que a correção mudou

- registro **por cópia de trabalho**, num diretório de registros, nunca um arquivo só
- subir **mata a pilha anterior** daquela cópia, inclusive a sem registro (reconhecida pelo
  diretório de trabalho do processo)
- um comando de **parar** que encerra a aplicação sem tocar nos bancos
- o comando de derrubar passou a **encerrar a aplicação junto** com os serviços
- a varredura **poupa** pilha cujo trabalho está em curso
- só mata o grupo quando o número registrado **lidera** o grupo — a primeira versão do
  teste derrubou o próprio terminal remoto por causa disso
- **log por cópia de trabalho**: dois ambientes simultâneos vinham se sobrescrevendo
