---
name: esteira-operar
description: Use para conduzir uma esteira de tarefas do ClickUp com o comando `orq` — ver o que está pronto e o que está bloqueado por dependência, saber quantas sessões a máquina aguenta agora, despachar sessões governadas em cópias de trabalho isoladas, acompanhar, e descobrir o que espera decisão humana. Use quando pedirem para rodar, despachar, priorizar ou conferir o andamento de uma esteira; quando perguntarem "o que eu devo tocar agora", "quantas sessões cabem aqui", "o que está travado", "dispare as próximas", "tem algo me esperando"; ou antes de abrir qualquer sessão longa em segundo plano para trabalho rastreado — a esteira dá a ela cópia de trabalho, ordem de serviço e canal de aviso que um lançamento improvisado não dá.
---

# Operar a esteira

`orq` transforma uma lista do ClickUp numa esteira que anda. Referência completa dos
comandos: `orq --help` e o `README.md` do repositório do orquestrador.

## Antes de qualquer coisa

```bash
orq doctor
```

Ele **prova** cada dependência por chamada real: o agente responde a um prompt, o ClickUp
devolve usuário e lista, o git cria e remove uma cópia de trabalho, o tmux abre e fecha uma
sessão. Nunca despache com o pré-voo vermelho — a versão antiga dele acreditava em
declaração, dava verde com token morto, e cada sessão morria dois segundos depois de
nascer enquanto o quadro ficava marcado como se alguém estivesse trabalhando.

## A divisão de autoridade — diga isto em voz alta quando importar

Três fontes de verdade que não se sobrepõem. Quase todo defeito de orquestração vem de
embaralhá-las:

| Pergunta | Quem manda | Por que não em outro lugar |
| --- | --- | --- |
| O que é esta unidade, em que estágio está, o que ela diz? | **ClickUp** | É o quadro do time, e o status **é** o estágio. Cópia local envelhece no instante em que alguém arrasta um cartão. |
| Qual a cadeia de estágios? O que depende de quê? O que barra? | **`<repo>/.orchestrator/pipeline.toml`** | Versionado junto com o código que governa, revisável em pull request. E o ClickUp não tem lugar bom para um grafo de dependências. |
| O que está rodando agora? | **Os processos vivos** | Uma marca de "rodando" gravada em disco sobrevive a um travamento e mente. O `orq` deriva isso a cada comando. |

Nada em `~/.claude/orchestrator/state/` é autoridade: são ordens de serviço, logs e um
histórico só-acrescenta para auditoria. Pode apagar tudo.

## A esteira é uma máquina de estados

Cada estágio nomeia três status do ClickUp:

| | |
| --- | --- |
| **fila** | onde a unidade espera; é daqui que o `orq` pega |
| **trabalho** | marcado ao lançar; prova que uma sessão é dona dela |
| **conclusão** | marcado ao terminar — e **é** a fila do estágio seguinte |

A cadeia anda porque a conclusão de um é a fila do outro. Não há segunda contabilidade.

**Dependência barra por estágio, não por unidade.** Para entrar no estágio S, cada
dependência precisa já ter passado do fim de S. Então B pode ser especificada enquanto A
ainda é implementada — é daí que vem quase toda a largura da esteira. A regra ingênua
("espere o bloqueador terminar") serializa uma esteira que poderia correr três de frente.

**Mas dependência de CÓDIGO é diferente.** A cópia de trabalho nasce do branch de
publicação: enquanto a dependência não estiver INTEGRADA, o código dela não existe na base.
Por isso as esteiras de código declaram `after = "integrate"`. Uma unidade já foi despachada
com `after = "review"`, encontrou a base sem nada do que precisava, e a sessão foi gasta à
toa.

## O ciclo

```bash
orq board           # o quadro inteiro, por estágio
orq next            # o que pode começar, em ordem de prioridade
orq dispatch -n 2   # dispara as duas de maior prioridade (confirma antes)
orq status -w       # acompanha; as linhas com ⚠ esperam uma pessoa
```

`orq run <unidade>` lança o estágio em que a unidade **está** — quem escolhe é o quadro,
não você. `--stage` só para refazer um.

## Capacidade: corrija por medida, nunca por palpite

```bash
orq capacity        # quantas sessões cabem, e por quê
orq host            # o que limita esta máquina agora
```

O teto sai do menor entre memória, processadores e carga. O orçamento é **por estágio**:
uma sessão de especificação lê código; uma de implementação dispara instalação, verificação
de tipos e testes. `orq capacity` mostra o consumo real das sessões vivas — ajuste o
`pipeline.toml` a partir dele. Um orçamento inventado, sete vezes acima do medido, já
serializou uma esteira inteira: a máquina admitia uma sessão por vez e o teto configurado
nunca era alcançado.

Em Linux com systemd, `orq host` lê a **fatia do usuário**, não a máquina. É o número que
importa: uma fatia pode estar sufocada com o medidor da máquina mostrando memória de sobra.

## O laço autônomo

```bash
orq loop --detach   # a esteira anda sozinha
orq loop-stop       # para o laço; as sessões em curso continuam
```

A cada ciclo ele reconsulta o ClickUp, recolhe unidades que ficaram em status de trabalho
sem sessão viva (arranque falho), devolve-as à fila e preenche a capacidade livre. Duas
falhas seguidas põem a unidade em quarentena, com aviso, em vez de repetir para sempre.

Ele para sozinho quando não há nada vivo nem pronto, quando fica ocioso demais, ou quando
o login cai. **Se parar sozinho, o primeiro lugar a olhar é `state/notify.log`**, que
registra o motivo.

## Quando parar e chamar uma pessoa

- A mesma unidade voltou reprovada duas vezes: o defeito provavelmente está na
  especificação, e isso é decisão humana.
- Uma unidade está em `parado`: alguém precisa responder algo. `orq status` mostra o quê.
- O pré-voo está vermelho.
- `orq host` acusa memória ou swap no teto.
- Uma tarefa aparece no quadro marcada como deriva: existe no ClickUp e não foi declarada.
  A esteira **nunca** executa o que não foi declarado — quem declara é uma pessoa.

Nunca feche um cartão por conta própria. Fechar é decisão humana.
