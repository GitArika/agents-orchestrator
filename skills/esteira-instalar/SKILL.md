---
name: esteira-instalar
description: Use para pôr a esteira para funcionar num projeto que ainda não a tem — criar o banco, declarar as unidades e dependências, criar os cinco status no ClickUp, e só entregar quando o pré-voo fechar verde. Use quando pedirem para "instalar a esteira aqui", "configurar o orquestrador neste projeto", "adotar isso no nosso repositório", ou quando alguém quiser saber se este projeto tem como rodar sessões governadas.
---

# Instalar a esteira num projeto

Você vai escrever no repositório de outra pessoa e no banco da esteira dela. Vale a regra
das skills que constroem: **examinar primeiro, apresentar o que pretende escrever, escrever
só depois do sim.**

## 1. Examinar o projeto antes de perguntar

`orq init` não lê nada do projeto sozinho — desde a decisão de 22/09/2026, o orquestrador
não declara mais portão nenhum. Quem examina é você:

| Pergunta | Onde procurar |
| --- | --- |
| Qual é o branch de publicação? | `git branch --show-current` na base, ou pergunte |
| O projeto tem `CLAUDE.md` ou `AGENTS.md` na raiz? | Se não tiver, **é bloqueador** — sem um dos dois o agente não tem de onde tirar setup/verificação, e `orq validate` recusa a esteira |
| Como se prepara o ambiente, e o que verifica antes de concluir? | O `CLAUDE.md`/`AGENTS.md` já declara — não é você quem decide isso, é conferir se está lá |
| O produto sobe serviço para trabalhar (banco, cache, fila)? | `docker-compose*.yml`/`.env.example` — se sim, `esteira-sandbox` |
| Qual o `owner/repo` no GitHub? | Necessário para o vigia de PR (OA-08) consultar `gh` |

## 2. Apresentar a proposta a uma pessoa

Em português comum, sem código como sujeito de frase:

- onde ficam as cópias de trabalho (fora do repositório, e por quê);
- que o setup e a verificação passam a ser o que o `CLAUDE.md`/`AGENTS.md` do projeto já
  diz — não algo que a esteira vai inventar ou manter à parte;
- que o encerramento de ambiente é fixo: se o produto sobe algo via
  `docker-compose*.yml`/`compose*.yml` na raiz da worktree, ele é derrubado sozinho quando a
  unidade sai de trabalho; qualquer outra coisa fica por conta do agente, na própria sessão;
- que a revisão passa a ser humana, no PR — não há mais uma sessão dedicada a revisar.

## 3. Criar o banco

```bash
orq init --repo . --base <branch de publicação> --worktrees <caminho FORA do repo> \
          --lista <id da lista> --github <owner>/<repo>
```

`--worktrees` tem de ficar fora do repositório: worktree dentro dele faz o `git status` do
repositório pai listar milhares de arquivos não rastreados.

## 4. Portões descobertos, nunca inventados

Se o `CLAUDE.md`/`AGENTS.md` não declara comando de verificação, **o portão não existe** —
diga isso à pessoa em vez de a esteira inventar um. Portão inventado falha por motivo
errado na primeira sessão, e o time conclui que a ferramenta não presta. Se não houver
nenhum dos dois arquivos, a esteira nem chega a ficar pronta: resolva isso primeiro.

## 5. Declarar as unidades e as dependências

```bash
orq task add <CHAVE> --clickup <id da tarefa> --titulo "..." [--prioridade normal] [--modo autonomous]
orq dep add <CHAVE> --precisa <OUTRA-CHAVE>    # pode repetir --precisa
```

Tarefa que existe no ClickUp e não foi declarada **nunca é executada** — não aparece nem
como deriva, simplesmente não existe para a esteira. Isso é proposital.

Dependência é sempre de **código**: a cópia de trabalho de uma unidade nasce do branch de
publicação, e o código de que ela depende só existe ali quando a dependência chegou a
`pronto` (fundida). Não há mais o conceito de dependência "de decisão" liberando mais cedo —
um papel só faz o ciclo inteiro, então todo o trabalho é código.

## 6. Os status no ClickUp

```bash
orq-clickup padronizar <listId> --cinco              # simula e mostra tudo
orq-clickup padronizar <listId> --cinco --aplicar
```

Ele recusa aplicar se houver tarefa em status que não é um dos cinco — mova-a antes. Leia o
aviso sobre herança de status: se a lista herda da pasta, `--substituir` liga a substituição
e ela deixa de acompanhar a pasta.

## 7. Ambiente fechado, se o projeto sobe serviço

Se trabalhar neste projeto exige subir banco, servidor ou qualquer processo, chame a skill
`esteira-sandbox` para construir o ambiente. **O encerramento não é mais configurável** — é
fixo, e só cobre o que subir por `docker-compose*.yml`/`compose*.yml` na raiz da worktree.
Se o comando que sobe o ambiente não usa Docker Compose, ele não tem reaper automático.

## 8. Entregar com o pré-voo verde

```bash
orq validate      # recusa uma esteira incoerente, sem escrever nada
orq doctor         # prova cada dependência por chamada real
```

Só entregue quando `orq doctor` fechar verde — e mostre a saída para a pessoa, linha por
linha. Se algo ficar vermelho, diga o que é e o que falta, em português comum.
