# OA-13 — A medição adaptada ao modelo novo

**Prioridade:** P2 · **Depende de:** OA-01, OA-08, OA-09, OA-11 · **Bloqueia:** nada

## Por que existe

`orq-medir` coleta de cinco fontes: sessões arquivadas (`meta.json`), despachos
(`runs.jsonl`), o estado do laço em JSON, os eventos de gancho, o registro de avisos e os
comentários das tarefas no ClickUp ([bin/orq-medir:634](../../../bin/orq-medir:634)). Três
dessas fontes mudam de forma nesta entrega e uma some. Sem adaptação, o painel continua
somando — com números errados, que é a pior falha possível num medidor.

E há oportunidade: a tabela `evento` de OA-01 é uma linha do tempo melhor do que qualquer
uma dessas fontes, porque é gravada na mesma transação do fato.

## Escopo

**Dentro:** trocar as fontes que mudaram, remover a dimensão de estágio, acrescentar as
métricas que o gate humano cria.

**Fora:** o painel em si (`modelos/painel.html`) muda só nos rótulos; o modelo de dados do
armazém de medição continua o mesmo.

## Desenho

### O que muda de fonte

| Hoje | Passa a ser |
| --- | --- |
| `state/loop-<esteira>.json` (strikes, quarentena, holds) | tabela `evento` do banco |
| `runs.jsonl` (despachos) | tabela `evento`, tipo `despachada` — o arquivo continua sendo escrito por compatibilidade, mas deixa de ser a fonte |
| dimensão `etapa` (spec/implement/review/integrate) | some; toda sessão é do papel único |
| comentários do ClickUp como linha do tempo | continua valendo (aprendizado nº 21: é o relógio que já se paga), lido por `orq-clickup` |

### As métricas novas que o gate humano cria

Três perguntas que o modelo anterior não sabia responder e que passam a ser as mais
importantes, porque agora o humano está no caminho crítico:

1. **Tempo em `revisao`** — do `pr_aberto` ao `pr_fundido`. É a espera humana, e com
   dependência liberando só no merge ela é o que determina a vazão da esteira.
2. **Taxa de devolução** — quantos PRs voltaram com `CHANGES_REQUESTED`, e quantas rodadas
   até fundir. É o termômetro da auto-revisão que OA-05 assume: subiu, a troca de revisor
   independente por gate humano está custando caro.
3. **Tempo de sessão do papel único** — a mediana por estágio some; o que fica é a
   distribuição de uma sessão inteira. Vale manter o alerta do modelo antigo: a
   implementação tinha mediana de 36 min com uma em cada dez passando de três horas, e a
   média enganava.

### Atribuição de código

Continua pelo **merge**, nunca pelo intervalo `base..branch` — o aprendizado nº 22
([docs/aprendizados.md:417](../../aprendizados.md:417)), em que uma base local 179 commits
atrás carimbou 91.270 linhas numa unidade só. Com o PR, isso fica mais fácil: o número do
PR está na unidade, e `gh pr view --json mergeCommit` dá o commit exato.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Coleta não quebra sem o JSON antigo | `orq-medir coletar` numa máquina que nunca teve o modelo velho → sai 0 |
| Nenhuma métrica vem de estágio | `grep -n "etapa" bin/orq-medir` → só leitura de arquivo histórico, marcada como tal |
| Tempo em revisão sai correto | Material de teste com `pr_aberto` e `pr_fundido` conhecidos → o resumo bate com o cálculo à mão |
| Taxa de devolução sai correta | Material com duas devoluções em três PRs → 66% |
| Arquivo histórico continua legível | Coletar sobre `testes/material/archive/` (modelo antigo) → sem exceção, marcado como legado |
| Atribuição pelo merge | Unidade com PR fundido → linhas atribuídas iguais às do `mergeCommit` |

## Riscos

- **Histórico misto.** Os arquivos de `testes/material/` e o que já foi coletado vêm do
  modelo de quatro estágios. A coleta precisa ler os dois sem misturar as contas — sessões
  legadas entram com `etapa` preenchida e as novas com `papel = 'auto-contido'`. Somar as
  duas populações numa mediana só produziria um número que não descreve nenhuma das duas.
- **Prioridade baixa de propósito.** Nada nesta unidade impede a esteira de rodar. Ela
  entra depois que o ciclo de ponta a ponta estiver de pé; o risco de antecipá-la é medir um
  desenho que ainda vai mudar.
