# OA-04 — O motor deixa de falar com o ClickUp

**Prioridade:** P0 · **Depende de:** OA-03 · **Bloqueia:** OA-05, OA-07, OA-12

## Por que existe

Hoje o motor consulta o ClickUp em todo ciclo: `fetch_board` pagina a lista inteira,
`status_order` busca o orderindex dos status, `set_status` e `comment` escrevem
([bin/orq:499](../../../bin/orq:499)–[bin/orq:546](../../../bin/orq:546)). Isso acaba. O
requisito é explícito: o orquestrador não faz mais ticks ao ClickUp, e a interação com o
quadro passa a ser responsabilidade dos agentes de sessão.

O ganho não é só de acoplamento. O laço passa a sobreviver a ClickUp fora do ar: hoje
`api()` chama `die()` em qualquer erro HTTP e o tick inteiro devolve
`fatal = "ClickUp inacessível"` ([bin/orq:2214](../../../bin/orq:2214)), parando a esteira
por indisponibilidade de uma ferramenta de gestão.

## Escopo

**Dentro:** remover do `bin/orq` toda chamada à API do ClickUp e tudo que só existia para
servi-la; mover o que o agente ainda precisa para `bin/orq-clickup`; ajustar o pré-voo.

**Fora:** `bin/orq-clickup` continua existindo e cresce (OA-07); a skill `esteira-clickup`
continua sendo o caminho de escrita dos agentes.

## Desenho

### O que sai de `bin/orq`

| Sai | Quem passa a fazer |
| --- | --- |
| `api()`, `API`, o token e `token_file` | `bin/orq-clickup`, que já tem os dois |
| `fetch_board()`, `status_order()` | ninguém — o status vive no banco (OA-03) |
| `set_status()` | o agente, por `orq-clickup`, seguindo o espelho de OA-07 |
| `comment()` e o comando `orq note` | o agente, por `orq-clickup comment` |
| `orq describe` | o agente, por `orq-clickup describe` |
| `orq show` lendo descrição e comentários | `orq show` passa a ler o banco (OA-03) |
| a prova de ClickUp no `orq doctor` | vira prova opcional, executada por `orq-clickup doctor` |

`orq note` e `orq describe` **não viram apelidos** que chamam o `orq-clickup` por baixo.
Apelido mantém o motor sabendo o que é ClickUp, que é o que esta unidade elimina; e deixa a
promessa "só fala com ClickUp" espalhada em dois binários. Os briefings passam a mandar o
agente usar `orq-clickup` diretamente (OA-05).

### O que fica no motor

Do ClickUp, só o **id** e a **URL** do cartão, gravados na unidade em OA-01. O motor não
sabe interpretar nenhum dos dois: são texto que ele repassa ao briefing.

### Efeito no laço

`tick()` deixa de ter o caminho `fatal: ClickUp inacessível`. Os únicos fatais que sobram
são "sem login no Claude Code" — e mesmo esse merece a ressalva do aprendizado nº 23
([docs/aprendizados.md:443](../../aprendizados.md:443)): `auth_ok()` confunde falta de
login com máquina sem capacidade de criar processo. Fica registrado como dívida conhecida
em OA-12, não resolvida aqui.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Nenhuma menção à API no motor | `grep -n "api.clickup\|CLICKUP_API_KEY" bin/orq` → vazio |
| A esteira anda com o ClickUp fora do ar | Teste: apontar o resolvedor para um host inalcançável e rodar `orq board`, `orq next`, `orq tick` → todos funcionam |
| Nenhum comando do motor pede token | `orq doctor` roda em máquina sem `credenciais.env` e só reclama do que o motor de fato usa |
| O agente continua conseguindo escrever | `orq-clickup comment <id> --text ...` publica, e a autoria é a da pessoa (aprendizado nº 16) |
| O quadro do ClickUp não é mais lido | `orq board` não faz nenhuma requisição de rede (provar com o host inalcançável acima) |

## Riscos

- **Deriva deixa de ser detectável pelo motor.** Hoje `classify` marca como deriva a tarefa
  que está no ClickUp e não na esteira ([bin/orq:1411](../../../bin/orq:1411)). Sem leitura
  do quadro, isso some. A promessa "a esteira só faz o que foi declarado" continua de pé
  (mais forte, até: só existe o que está no banco), mas ninguém avisa que há cartão novo
  esquecido. Mitigação fora desta entrega: um `orq-clickup diff --banco` rodado à mão pela
  sessão de planejamento.
- **O quadro do ClickUp pode divergir do banco** se um agente morrer entre escrever no banco
  e escrever no cartão. A ordem definida em OA-05 (banco primeiro, cartão depois) torna a
  divergência visível no cartão, que é o lugar onde uma pessoa olha — e o rastro do banco
  permite recompor. Não há transação distribuída aqui, e fingir que há seria pior.

## Nota de implementação (22/09/2026)

**O escopo real ficou maior que a letra original deste spec.** OA-01/OA-02/OA-03 já
prometiam, nas próprias palavras ("até OA-04 remover pipeline.toml por inteiro"), que esta
unidade encerraria o motor TOML inteiro — não só as chamadas ao ClickUp. Confirmado com
você: removido tudo, aceitando o hiato funcional até OA-05.

Saiu de `bin/orq` (4187 → 1597 linhas): `Config`/`Unit`/`Stage`, `find_config` e o
resolvedor de esteira por diretório, o write-guard (`deve_recusar`/`comando_so_le`/
`SO_LEEM`), `api`/`fetch_board`/`status_order`/`set_status`/`comment`, as quatro
templates de briefing (`BRIEFS`/`CONTEXT`/`SEM_NAVEGADOR`/`COMMON`), `launch`/
`ensure_worktree`/`ensure_trusted`/`argumentos_new_session`/`settings_json`/
`cerca_impressao`, `finalize`/`archive_dir`/`anotar_evento`/`rodar_teardown`, `classify`/
`ready_queue`/`load`, o laço antigo (`tick`/`loop_state`/`notify`/`auth_ok`/`cmd_loop`), o
pré-voo (`cmd_doctor` e as `_prova_*`), e os oito comandos que já estavam `_toml_legado`
desde OA-03, mais `run`/`dispatch`/`capacity`/`sweep`/`archive`/`reset`/`reject`/
`unquarantine`/`note`/`describe`/`attach`/`log`/`stop`/`brief`.

**Consequência aceita:** `orq run`, `orq dispatch`, `orq doctor` e `orq capacity` não
existem entre esta entrega e as próximas. A esteira não consegue lançar uma sessão nova
até OA-05 dar a ela um lançador de verdade contra o banco, nem tem pré-voo até OA-12. Os
dezesseis comandos que sobraram (`init/task/dep/config/export/validate/board/next/status/
show/advance/hold/release/reopen/tick/host`) funcionam de ponta a ponta — confirmado por
`orq --help`, pela suíte (183 testes) e por um ciclo manual completo com o ClickUp
estruturalmente inalcançável (o binário não importa mais `urllib` nenhum).

`testes/test_orq.py` perdeu as seis classes que testavam funções removidas
(`teto_do_estagio`, `argumentos_new_session`, `build_brief`, `esteiras_desta_maquina`,
`conta_falta`, `deve_recusar`, `comando_so_le`, `unidades_disputadas`); ficaram as que
testam o que sobreviveu (cgroup/memória, `divergencia_de_maquina`, reaproveitada por
`resolver_banco`).
