# Medição

A esteira produz rastro em vários lugares que não conversam entre si — o mais rico deles,
desde o modelo de papel único, é o próprio banco SQLite da esteira: cada fato vira um evento
gravado na mesma transação, com hora exata. Isto junta tudo num armazém só e responde, por
unidade de trabalho, quanto tempo levou, quantas vezes voltou, quanto esperou por uma
pessoa, quantos tokens consumiu e quanto código produziu.

## Os cinco comandos

```bash
orq-medir esquema     # cria ou atualiza o armazém
orq-medir coletar     # varre tudo e preenche; seguro repetir à vontade
orq-medir resumo      # os números na tela
orq-medir exportar    # o JSON bruto de tudo
orq-medir servir      # o painel, no endereço local
```

Comece pelo `resumo`. Ele responde "o que esta esteira produziu até agora" — incluindo as
três métricas que o gate humano criou (abaixo).

`coletar --sem-rede` pula a consulta ao ClickUp (comentários), quando você quiser rodar sem
internet ou sem gastar chamada. A leitura do banco da esteira não depende de rede.

## O painel

Um serviço serve o painel de dentro da máquina, e a coleta roda a cada cinco
minutos. A página se atualiza sozinha: o quadro do agora a cada 15 segundos, os
números históricos a cada minuto.

**Ele escuta só no endereço local, e isso é decisão de segurança, não descuido.**
O painel carrega título de tarefa, texto de comentário e nome de branch — coisa
interna do projeto. Para abrir de outra máquina, faça um túnel:

```bash
ssh -N -L 8791:127.0.0.1:8791 orq@<endereço da vps>
```

e abra `http://127.0.0.1:8791`. A porta está registrada em
`~/.claude/orchestrator/state/painel.porta`; troque se ela já estiver ocupada
por outra coisa na máquina.

```bash
systemctl --user status orq-medir-painel.service    # o servidor
systemctl --user list-timers orq-medir.timer        # a próxima coleta
```

Abrir o arquivo do painel direto no navegador **não funciona**: ele busca os
dados por HTTP, de propósito, para não precisar ser regerado a cada mudança.

## As três métricas que o gate humano criou (OA-13)

Com o humano no caminho crítico — não há mais sessão de revisão, só uma pessoa olhando o
PR —, o que determina a vazão da esteira é a espera por ela. Três perguntas novas:

**Tempo em revisão.** Do evento `pr_aberto` ao `pr_fundido`, por unidade. É a espera humana
de verdade, medida, não deduzida.

**Taxa de devolução.** Quantos PRs voltaram com `CHANGES_REQUESTED` (evento `retrabalho`), e
quantas rodadas até fundir. É o termômetro da auto-revisão que o papel único assume: se
subir, a resposta é considerar um revisor automático antes do PR — nunca afrouxar o gate
humano.

**Duração da sessão de papel único.** A mediana por estágio (spec/implement/review/
integrate) deixou de existir — não há mais estágio. O que fica é a distribuição da sessão
inteira, de ponta a ponta.

## De onde cada número sai

| Pergunta | De onde a resposta sai |
| --- | --- |
| Quantas sessões houve e como terminaram | a tabela `sessao` do banco da esteira (medido: início e fim são a mesma transação do despacho e do encerramento) |
| Tempo em revisão, taxa de devolução, quando cada coisa aconteceu | a tabela `evento` do banco da esteira — append-only, com hora exata |
| Quantos tokens custou, por modelo | as transcrições das cópias de trabalho |
| Quanto código saiu, e de qual PR | o commit que integrou cada PR — achado pelo **número do PR**, não pelo nome do branch, cobrindo merge tradicional e squash |
| O histórico dos comentários da tarefa | os comentários no ClickUp, lidos direto (aprendizado nº 21: é o relógio que já se paga) |

**Rastro do modelo antigo** (pastas de sessão arquivadas, `runs.jsonl`, o estado do laço em
JSON) continua sendo lido — para não perder o que já foi coletado antes da troca —, mas
nunca é a fonte para uma unidade nova. As duas populações não se somam: sessão do modelo
antigo entra marcada por etapa; sessão do modelo novo entra com a sentinela
`auto-contido`, e o resumo mostra as duas separadas.

## Onde as coisas ficam

O armazém é um arquivo em `~/.claude/orchestrator/state/medicao.db`. É um banco
SQLite: se você tem o `sqlite3` instalado, consulta direto; se não, o Python da
casa lê sem instalar nada.

Vistas prontas incluem `v_ciclo_por_unidade`, `v_retrabalho`, `v_espera_humana`,
`v_consumo_por_unidade`, `v_producao_por_unidade`, `v_tempo_revisao` e `v_devolucao`.

## A coleta automática

Um temporizador do sistema roda a cada cinco minutos, em prioridade baixa:

```bash
systemctl --user list-timers orq-medir.timer     # quando roda de novo
systemctl --user start orq-medir.service         # rodar agora
journalctl --user -u orq-medir.service -n 30     # o que aconteceu
```

Ele **abre o banco da esteira em modo somente leitura** e escreve exclusivamente no próprio
armazém. Não disputa memória com as sessões e nunca toca no estado da esteira.

## O que ele NÃO mede, e por quê

**Resultado de portão fica de fora.** Ele só existe dentro da captura de
terminal, em texto corrido com códigos de cor. Interpretar aquilo é caro e
frágil. As capturas continuam guardadas como evidência de última instância.

**Custo em dinheiro não é calculado** enquanto ninguém preencher a tabela
`preco_modelo`. Preço é regra de negócio: sem ele cadastrado, o resumo diz que
não sabe, em vez de inventar um número. Tokens continuam contados.

**Nada anterior a 31/08/2026** tem rastro. A esteira só passou a arquivar sessão
a partir dali.

**Integração por rebase não é atribuída pelo PR.** Rebase não carimba o número do PR em
lugar nenhum; a atribuição cai no caminho antigo, por nome de branch, que só acerta se o
branch não tiver sido apagado.

## Duas armadilhas que já custaram tempo

**O tempo em cada status do quadro é recurso pago.** A chamada responde
`TIS_027 — Time In Status is not available on your plan`, e o endereço de
histórico da tarefa não existe mais. O relógio vem dos comentários, que são de
graça e ainda dizem o que aconteceu e quem assinou.

**A base local do repositório envelhece sem avisar.** Atribuir commit a unidade
pelo intervalo `base..branch` parece certo e está errado: com a base atrasada, o
intervalo devolve o trabalho de todas as unidades, e a atribuição fica com quem
rodou por último. A atribuição sai do **merge** — hoje, de preferência, achado pelo número
do PR que já está na unidade, não por regex no assunto do commit.
