# OA-07 — O espelho de cinco status no ClickUp

**Prioridade:** P1 · **Depende de:** OA-04, OA-05 · **Bloqueia:** OA-14

## Por que existe

A lista do ClickUp hoje tem dez status canônicos, herdados dos quatro estágios. Com cinco
estados na esteira, o quadro passa a ter os mesmos cinco, com o mesmo nome — decisão de
21/09/2026, "espelho exato". E como o motor não escreve mais no ClickUp (OA-04), quem
mantém o espelho é o agente; sem um contrato explícito, cada sessão escolheria o nome que
achasse melhor e o quadro pararia de significar alguma coisa.

## Escopo

**Dentro:** os cinco status no ClickUp, o provisionamento deles por `orq-clickup`, o
contrato de escrita do agente e o que ele comenta em cada transição.

**Fora:** a máquina de estados em si (OA-03), o briefing (OA-05).

## Desenho

### Os cinco, e só eles

| Esteira | ClickUp |
| --- | --- |
| `backlog` | **backlog** |
| `em_progresso` | **em progresso** |
| `revisao` | **revisão** |
| `pronto` | **pronto** (status de fechamento da lista) |
| `bloqueado` | **bloqueado** |

O provisionamento vira `orq-clickup padronizar <lista> --cinco`, e ele precisa fazer o que
o aprendizado nº 17 ensinou: **reler e comparar depois de escrever**
([docs/aprendizados.md:318](../../aprendizados.md:318)). A lista herda status da pasta, e
sem ligar a substituição a API responde 200 e ignora o pedido. O comando sai != 0 se a
releitura não devolver exatamente os cinco.

Listas que já estão em uso com os dez status precisam de conversão consciente: o comando
imprime quantas tarefas estão em cada status que vai desaparecer e **recusa** enquanto
houver tarefa num status órfão. Mover tarefa dos outros é decisão de quem toca o quadro.

### O contrato do agente

Duas escritas obrigatórias por sessão, sempre **depois** da escrita no banco (OA-05):

1. Ao começar: status → **em progresso**, sem comentário (o Telegram já avisa; comentário
   a cada início vira ruído no cartão).
2. Ao encerrar:
   - abriu PR → status **revisão** + comentário com a URL do PR, os critérios de aceite
     com evidência e a saída dos portões;
   - travou → status **bloqueado** + comentário `AGUARDANDO DECISÃO HUMANA: <motivo>`.

A transição para **pronto** é escrita pelo **vigia de PR** (OA-08), não pelo agente — quando
o merge acontece a sessão já morreu há tempo. É a única escrita no ClickUp que não parte de
uma sessão, e ela sai por `orq-clickup`, chamado pelo laço.

> Nota de coerência: OA-04 tira o ClickUp do motor. O vigia chama o **binário**
> `orq-clickup` como subprocesso, não a API — a fronteira continua num arquivo só, e o laço
> continua sobrevivendo ao ClickUp fora do ar (falha de escrita do espelho registra evento e
> **não** impede a transição no banco).

### Autoria

Continua valendo o aprendizado nº 16: o token é pessoal e tudo sai assinado pela pessoa dona
da esteira. Toda escrita passa por `orq-clickup`, nunca por outro caminho autenticado —
é a regra que existe porque uma aprovação já foi publicada com o nome de quem não aprovou.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| A lista fica com exatamente cinco status | `orq-clickup list <id> --json` → cinco, com `override_statuses` ligado |
| O provisionamento não acredita na API | Teste com lista que herda da pasta: o comando sai != 0 e diz que a releitura não bateu |
| Conversão recusa tarefa órfã | Lista com tarefa em "aguardando revisão" → recusa nomeando a tarefa |
| O agente escreve os dois lados | Ciclo completo: evento no banco e status no cartão coincidem ao fim |
| Falha do ClickUp não trava a esteira | Token inválido → `orq advance` grava no banco, registra o evento `espelho_falhou` e retorna 0 |
| `pronto` é escrito pelo vigia | Fundir o PR → cartão vai a "pronto" sem nenhuma sessão viva |

## Riscos

- **Divergência silenciosa.** Se a escrita do espelho falhar e ninguém olhar o evento, o
  cartão fica mentindo. Mitigação: `orq board` marca com `⚠` a unidade cujo último
  `espelho_falhou` é mais recente que o último `espelho_ok`, e o Telegram avisa (OA-11).
- **Cinco status podem não bastar para o time.** O quadro perde granularidade que algumas
  pessoas usavam para planejar ("spec pronta" dizia que dava para estimar). Isso é decisão
  tomada; se voltar como problema, a saída é um mapa configurável, não status escondido.
