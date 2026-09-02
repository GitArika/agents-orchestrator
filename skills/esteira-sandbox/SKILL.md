---
name: esteira-sandbox
description: Use quando uma sessão precisar rodar o produto de verdade para provar alguma coisa — entrar no sistema, abrir uma tela de dentro, conferir critério visual, medir comportamento que teste de unidade não prova. Ergue um ambiente fechado e local para ESTE projeto: bancos e serviços em Docker presos ao loopback, usuários inventados pelo próprio orquestrador, nada de dado real e nada de base de homologação. Use também quando pedirem para preparar, semear, conferir ou derrubar o ambiente de teste, e quando uma sessão for parar por falta de credencial.
---

# Erguer o ambiente fechado deste projeto

Isto não é uma ferramenta pronta que você configura. É um roteiro para **construir** o
ambiente do projeto onde você está. Examine, apresente, escreva depois do sim.

## Por que existe

Para conferir qualquer tela de dentro do produto, a sessão precisa entrar. Entrar precisa
de usuário. E a única fonte de usuário que costuma existir é a base de homologação — gente
de verdade, dados de verdade, credencial de alguém. Isso não se dá a uma sessão
desacompanhada.

Aqui os serviços sobem em Docker no loopback e o próprio orquestrador inventa os usuários.

## 1. Descobrir o que este projeto é

Antes de escrever qualquer coisa:

| Pergunta | Onde procurar |
| --- | --- |
| Que serviços o produto precisa? | `docker-compose*.yml`, `.env.example`, drivers nas dependências |
| Como ele se conecta? | nomes de variáveis: `*_URI`, `*_URL`, `*_HOST`, `*_PORT` |
| Como se autentica? | rotas de login, tabela ou coleção de usuários, papéis |
| Que comando sobe cada parte? | scripts do projeto, `Procfile`, `Makefile` |
| A configuração aponta para onde hoje? | o `.env` do repositório — **nunca reutilize**, sobreponha |

Apresente o que achou a uma pessoa antes de escrever. Se não achar como o produto
autentica, **pergunte**; não invente um fluxo de login.

## 2. O que você produz

Em `<projeto>/.orchestrator/sandbox/`: os serviços em Docker, um semeador de usuários, um
subidor da aplicação e o encerramento. E a ligação no `pipeline.toml`:

```toml
[gates]
setup    = ["...", "orq-sandbox up && orq-sandbox seed"]
teardown = ["orq-sandbox parar --worktree $PWD"]
```

## Regras que não se negociam

**Portas próprias, longe das de desenvolvimento.** Colidir com elas faria a sessão escrever
no banco de verdade achando que está no ambiente fechado — o pior desfecho possível aqui.

**Loopback sempre, e o semeador RECUSA outro endereço.** Sem bandeira que destrave. Ele cria
usuários com senha conhecida; apontá-lo para um ambiente de verdade seria abrir uma porta
dos fundos.

**Usuários inventados**, em domínio reservado que nunca resolve, com senha aleatória por
instalação, um por papel. Nenhuma pessoa real, nenhum dado real.

**Sobreponha a configuração por ambiente, não editando arquivo.** Carregadores de
configuração costumam preencher apenas o que ainda não existe no ambiente — então variável
exportada vence o arquivo do repositório, e o arquivo que aponta para homologação fica
intocado no disco, perdendo por precedência. Isso é mais seguro do que editar e lembrar de
desfazer.

**Saída dos servidores vai para ARQUIVO, nunca para cano.** Com cano, soltar o servidor mata
o filho no primeiro `write` depois que o pai sai — e você vai depurar um "servidor que morre
sozinho" que na verdade levou um EPIPE. Arquivo também dá o log depois.

## As cinco regras do encerramento

Estas cinco vieram de um vazamento real: 27 ambientes sobreviveram a uma noite, 147
processos, 8,8 GB presos, o swap da fatia cheio e mais de um milhão de freadas por memória —
com o medidor da máquina mostrando 16 GB livres.

1. **Um registro por cópia de trabalho**, nunca um só. Registro único e sobrescrito apaga o
   rastro da subida anterior, e ninguém mais sabe os números dos processos que ficaram
   vivos. Foi exatamente essa a causa.
2. **Subir mata a pilha anterior daquela cópia** — inclusive a que não deixou registro,
   reconhecida pelo diretório de trabalho do processo.
3. **Mate o GRUPO, não o processo.** A casca é só um `sh -c`; quem come memória são os
   filhos. E **só mate o grupo se o número registrado liderar o próprio grupo**: em shell
   não interativo, `&` não cria grupo novo, e matar grupo alheio derruba quem chamou. Já
   aconteceu, num teste, com o próprio terminal.
4. **A varredura poupa trabalho em curso.** Uma pilha sem registro pode estar sendo usada.
   Confira antes de matar — pelo nome da cópia de trabalho, contra as sessões vivas.
5. **Derrubar containers não é derrubar a aplicação.** São duas coisas; o comando que
   derruba os serviços precisa derrubar os processos também.

E o encerramento tem de estar no `teardown` da esteira, que roda **em todo caminho de
saída da sessão, inclusive quando ela morre**. Encerramento que depende da boa vontade da
sessão não acontece: a sessão pode morrer.

## Log por cópia de trabalho

Log único faz duas sessões simultâneas se sobrescreverem, e o diagnóstico aponta para o
lugar errado. Nomeie o log pela cópia de trabalho.

## Referência

`referencia-esteira-sandbox.md`, ao lado deste arquivo: uma implementação real, com os números do
vazamento e o que cada decisão evitou.
