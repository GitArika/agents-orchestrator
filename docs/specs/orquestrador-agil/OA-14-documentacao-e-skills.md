# OA-14 — Documentação e skills do modelo novo

**Prioridade:** P2 · **Depende de:** OA-02, OA-05, OA-07, OA-12 · **Bloqueia:** nada

## Por que existe

Oito skills e oito documentos descrevem um sistema que deixa de existir: quatro estágios,
dez status, `pipeline.toml`, `orq reject`, sessão de integração que funde. Skill errada é
pior que skill ausente — um agente a carrega, confia nela e faz o que ela manda. Já
aconteceu na casa: uma unidade relançada recebeu ordem de serviço nova com skill velha e
foi fazer à mão o que já tinha comando.

## Escopo

**Dentro:** reescrever o que descreve o funcionamento; apagar o que descreve peça removida.

**Fora:** a skill de planejamento da esteira (fora desta entrega, decisão de 21/09/2026) —
o espaço dela fica reservado no índice da documentação, com a nota de que a declaração é
feita pelos verbos de OA-02.

## Desenho

### Documentos

| Arquivo | O que muda |
| --- | --- |
| `README.md` | Os cinco comandos, os cinco status, o papel único, o gate humano; a tabela "o que uma corrida real produziu" vira histórica, com a nota de que os números são do modelo de quatro estágios |
| `docs/operacao.md` | Quadro novo, `orq release`, vigia de PR, o que fazer quando o PR volta |
| `docs/clickup.md` | Cinco status espelho (OA-07); quem escreve é o agente, nunca o motor |
| `docs/instalacao.md` | `orq init` sem TOML; credenciais do Telegram; `gh` autenticado como requisito |
| `docs/seguranca.md` | A cerca nova: publica o próprio branch, nunca funde; o banco na lista de intocáveis |
| `docs/host-linux.md` | Destino de aviso passa a ser Telegram |
| `docs/medicao.md` | Métricas novas (tempo em revisão, taxa de devolução) |
| `docs/aprendizados.md` | **Não se reescreve.** É registro histórico; os aprendizados que motivaram decisões desta entrega ganham uma linha apontando para o spec correspondente |
| `modelos/pipeline.toml` | **Removido.** Junto com o código que o lia |

### Skills

| Skill | Destino |
| --- | --- |
| `esteira-operar` | Reescrita: cinco status, vigia de PR, gate humano |
| `esteira-sessao` | Reescrita: é o contrato do papel único (OA-05) — dois encerramentos, não três |
| `esteira-instalar` | Reescrita: `orq init` + verbos, sem provisionar dez status |
| `esteira-clickup` | Atualizada: cinco status, `padronizar --cinco`, e continua sendo o **único** caminho de escrita no quadro |
| `esteira-diagnosticar` | Atualizada: sintomas do banco, do `gh`, do Telegram; remove os sintomas de peças que sumiram |
| `esteira-host` | Atualizada: credenciais do Telegram no provisionamento |
| `esteira-sandbox`, `esteira-navegador` | Sem mudança estrutural; revisar menções a estágio |
| `pipeline-orchestrator` (em inglês) | Alinhar com `esteira-operar` ou remover, para não haver duas descrições divergentes do mesmo sistema |

### A regra de ouro desta unidade

Nenhum documento afirma comportamento que não foi provado. Onde a entrega trocou uma prática
por outra, o texto diz **o que era, o que passou a ser e por quê** — é o que dá aos
documentos desta casa o valor que eles têm, e é o que impede a próxima pessoa de refazer a
decisão por não saber que ela foi tomada.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Nenhuma menção a peça removida | `grep -rn "pipeline.toml\|orq reject\|estágio de integração\|spec pronta" README.md docs/ skills/` → só ocorrências em `aprendizados.md` (histórico) |
| Nenhuma skill manda fundir | `grep -rn "gh pr merge" skills/` → vazio |
| Os cinco status aparecem iguais nos três lugares | Comparar `docs/clickup.md`, `skills/esteira-clickup`, e o `CHECK` do esquema em OA-01 |
| Quem chega entende em dez minutos | `docs/para-quem-chega.md` descreve o ciclo real de ponta a ponta |
| Números históricos marcados | A tabela de resultados do README diz de qual modelo ela veio |

## Riscos

- **Documentação escrita antes do código estabilizar envelhece na mesma semana.** Por isso
  P2 e por isso depende de OA-12: só depois que o pré-voo passa verde no modelo novo é que
  o comportamento está estabelecido o bastante para ser descrito.
