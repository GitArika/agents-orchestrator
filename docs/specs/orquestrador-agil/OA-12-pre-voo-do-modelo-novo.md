# OA-12 — O pré-voo do modelo novo

**Prioridade:** P1 · **Depende de:** OA-02, OA-04, OA-06, OA-10 · **Bloqueia:** OA-14

## Por que existe

`orq doctor` é o comando que a documentação manda rodar antes de tudo e sempre que algo
parece estranho. Metade do que ele prova hoje deixa de existir (ClickUp, estágios,
`pipeline.toml`) e metade do que passa a importar ele não prova (banco, `gh`, Telegram).
Pré-voo que dá verde no modelo errado é pior do que pré-voo nenhum — é a lição nº 1 da casa:
o pré-voo dizia que estava tudo bem e cada sessão morria em dois segundos.

## Escopo

**Dentro:** reescrever a bateria do `doctor`, cada prova por chamada real; manter a regra de
que prova que não pode ser feita de verdade não vira verde.

**Fora:** o validador de declaração (`orq validate`, OA-02) — o `doctor` o **chama**, não o
duplica.

## Desenho

### As provas

| Prova | Como (chamada real) | Fatal? |
| --- | --- | --- |
| Banco abre e é desta máquina | abre, lê `esquema.versao`, compara `repo` com o `git-common-dir` atual | sim |
| WAL ativo e disco local | `PRAGMA journal_mode` = `wal`; recusa banco em sistema de arquivos de rede | sim |
| A fila funciona | dois escritores concorrentes numa unidade de teste; ambos completam, nenhum perde | sim |
| Declaração coerente | chama `orq validate` | sim |
| Agente sobe | lança uma sessão descartável e confirma que ela responde | sim |
| `gh` na PATH e autenticado | `gh auth status`; e `gh pr list --repo <github_repo> --limit 1` | sim |
| Git com credencial não interativa | como hoje ([bin/orq:2781](../../../bin/orq:2781)) | sim |
| `tmux` ≥ 3.2 | como hoje — a opção `-e` é o que dá ambiente por sessão | sim |
| Cerca presente e íntegra | existe, executável, impressão SHA registrada, `testes/cerca.sh` verde | sim |
| Confiança de pasta herdável | o repositório base está marcado como confiável | sim |
| Worktree root fora do repo | comparação de caminho | sim |
| Telegram entrega | `orq-avisar --testar` e confere `ok: true` | não — avisa |
| Capacidade | RAM livre, fatia do cgroup, carga (preservado de [bin/orq:585](../../../bin/orq:585)) | não |

### O que sai

A prova de ClickUp deixa o `doctor` do motor (OA-04). Ela não some: vira
`orq-clickup doctor --lista <id>`, que o agente pode rodar e a instalação recomenda. Motivo:
o motor não depende mais do ClickUp para funcionar, e um pré-voo que falha por causa de uma
ferramenta de gestão indisponível impediria despacho sem necessidade.

### A dívida que fica registrada

`auth_ok()` diz "sem login" quando a máquina é que não consegue mais criar processo
(aprendizado nº 23, [docs/aprendizados.md:443](../../aprendizados.md:443)). O `doctor` passa
a **distinguir**: antes de concluir "sem login", tenta criar um processo trivial; se isso
falhar, o diagnóstico é "a máquina não consegue mais criar processo", com o número de
processos e o limite. É correção barata e evita a caça errada — a mesma que custou uma
madrugada.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Nenhuma prova é de mentira | Ler a saída: cada linha traz a evidência (versão, id, caminho, resposta) |
| Banco de outra máquina não dá verde | Copiar um banco com `repo` de outra máquina → prova falha com o caminho divergente |
| A prova de fila realmente concorre | Instrumentar: as duas transações se sobrepõem no tempo e ambas completam |
| `gh` desautenticado é fatal | `GH_TOKEN` inválido → `doctor` sai != 0 dizendo `gh auth login` |
| Telegram ausente avisa, não mata | Sem credencial → linha amarela, código de saída 0 |
| Falta de processo não vira "sem login" | Simular limite de processos → a mensagem fala de processo, não de login |
| O `doctor` roda sem ClickUp | Sem `credenciais.env` → verde (com o Telegram amarelo) |

## Riscos

- **Pré-voo longo é pré-voo que ninguém roda.** A prova de sessão descartável e a de fila
  custam segundos; o alvo é o conjunto inteiro abaixo de 30s. Se passar disso, o corte é
  ter um `--rapido` que pula as duas mais caras, nunca transformá-las em verde presumido.
- **A prova de fila escreve no banco.** Ela usa uma unidade de teste com chave reservada
  (`__doctor__`) e a remove ao fim, na mesma transação. Deixar lixo no banco de produção
  seria trocar um problema por outro.
