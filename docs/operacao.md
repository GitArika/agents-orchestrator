# Operação no dia a dia

## Os cinco comandos

```bash
orq doctor       # está tudo de pé? prova cada peça de verdade
orq board        # o quadro: o que está pronto, travado, rodando
orq next         # o que pode começar agora, em ordem
orq dispatch -n 2   # dispara as duas mais importantes
orq status       # o que está vivo e o que espera você
```

Comece o dia pelo `orq status`. Ele é a resposta para "tem alguma coisa me esperando?".

## Lendo o quadro

O `orq board` mostra cada tarefa e em que situação ela está:

| O que aparece | O que significa | O que fazer |
| --- | --- | --- |
| **pronta** | pode começar agora | `orq dispatch` |
| **bloqueada** | espera outra tarefa terminar | nada; ela anda sozinha |
| **rodando** | tem uma sessão trabalhando nela agora | `orq log <tarefa> -f` para acompanhar |
| **travada** | a sessão acabou sem se despedir | `orq reset <tarefa>` devolve à fila |
| **em quarentena** | falhou duas vezes seguidas | olhe o que houve antes de soltar |
| **deriva** | está no ClickUp e não no arquivo da esteira | declare, ou ignore de propósito |

## Quando a esteira espera você

Uma tarefa em **parado** significa: alguém precisa responder alguma coisa. O motivo está no
comentário do cartão e em `orq status`.

Depois de responder:

```bash
orq release <tarefa>
```

Ela volta exatamente para o status de onde saiu.

Se a máquina não tem tela — um servidor —, configure um destino de aviso. Sem isso, a espera
é silenciosa e a esteira parece travada sem motivo. Está em [Host Linux](host-linux.md).

## Deixar andando sozinha

```bash
orq loop --detach     # a esteira anda sozinha
orq loop-stop         # para; as sessões em curso continuam
```

A cada ciclo ela reconsulta o ClickUp, recolhe o que morreu no meio, e preenche a capacidade
livre. Duas falhas seguidas na mesma tarefa põem a tarefa de castigo, com aviso, em vez de
repetir para sempre.

**Se o laço parar sozinho**, o motivo está registrado:

```bash
cat ~/.claude/orchestrator/state/notify.log
```

## Quantas sessões cabem

```bash
orq capacity      # o teto agora, e por quê
orq host          # o que está limitando a máquina
```

O número sai do menor entre memória, processadores e carga. **Corrija o orçamento por
medida, não por palpite:** o `orq capacity` mostra o consumo real das sessões vivas. Um
palpite sete vezes acima do real já fez uma máquina admitir uma sessão por vez, quando
caberiam oito.

## Como uma sessão termina

Toda sessão termina de um destes três jeitos, e você vai ver isso no cartão:

- **concluiu** — a tarefa avançou para a etapa seguinte;
- **reprovou** — voltou para quem pode corrigir, com os achados escritos;
- **travou** — foi para "parado" e está esperando uma pessoa.

Se uma sessão acabar sem nenhum dos três, a tarefa aparece como **travada** no quadro. Ela
nunca some.

## Quando alguma coisa está estranha

```bash
orq doctor        # começa por aqui, sempre
```

Se não resolver, a skill `esteira-diagnosticar` tem a lista de sintomas já conhecidos, com a
causa provada de cada um. E os [Aprendizados](aprendizados.md) contam as histórias
completas.
