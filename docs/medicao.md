# Medição

A esteira rodou uma corrida inteira e não sabia dizer quanto produziu. O rastro
existia — em seis lugares que não conversavam. Isto junta.

## Os cinco comandos

```bash
orq-medir esquema     # cria ou atualiza o armazém
orq-medir coletar     # varre tudo e preenche; seguro repetir à vontade
orq-medir resumo      # os números na tela
orq-medir exportar    # o JSON bruto de tudo
orq-medir servir      # o painel, no endereço local
```

Comece pelo `resumo`. Ele responde "o que esta esteira produziu até agora".

`coletar --sem-rede` pula a consulta ao quadro, quando você quiser rodar sem
internet ou sem gastar chamada.

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

## Memória por sessão e por etapa

A coleta lê o consumo real de cada sessão viva — pelo tmux, somando o grupo de
processos — e guarda uma amostra por tarefa por minuto.

**Isto só existe daqui para a frente.** O rastro antigo nunca guardou consumo por
sessão, e nada recupera o que jamais foi escrito. A vista
`v_memoria_por_etapa` fica vazia até a primeira coleta com sessão rodando.

Vale registrar por que foi feito assim: o motor **sabe** medir isso e não grava.
Medir por fora, a partir do tmux, é aditivo — não toca numa linha do motor, e
por isso pôde ser feito com a esteira em voo.

## O que ele mede

| Pergunta | De onde a resposta sai |
| --- | --- |
| Quantas sessões houve e como terminaram | as pastas de sessão arquivadas |
| Quando cada sessão começou | o registro de despachos |
| Quantas vezes a unidade voltou | os desfechos de reprovação, mais o estado do laço |
| Quanto tempo ficou esperando uma pessoa | as esperas registradas no laço |
| Quantos tokens custou, por modelo | as transcrições das cópias de trabalho |
| Quanto código saiu | os merges no repositório do produto |
| Quem decidiu o quê, e quando | os comentários das tarefas no quadro |

## Onde as coisas ficam

O armazém é um arquivo em `~/.claude/orchestrator/state/medicao.db`. É um banco
SQLite: se você tem o `sqlite3` instalado, consulta direto; se não, o Python da
casa lê sem instalar nada.

Cinco vistas prontas: `v_ciclo_por_unidade`, `v_retrabalho`, `v_espera_humana`,
`v_consumo_por_unidade` e `v_producao_por_unidade`.

## A coleta automática

Um temporizador do sistema roda a cada cinco minutos, em prioridade baixa:

```bash
systemctl --user list-timers orq-medir.timer     # quando roda de novo
systemctl --user start orq-medir.service         # rodar agora
journalctl --user -u orq-medir.service -n 30     # o que aconteceu
```

Ele **só lê o que já terminou** — pasta de sessão arquivada e transcrição
encerrada — e escreve exclusivamente no próprio armazém. Não disputa memória com
as sessões e não toca no estado da esteira.

## O que ele NÃO mede, e por quê

**Duração de sessão é deduzida, não medida.** O motor não grava início e fim; o
que existe é a hora do despacho e a hora do arquivamento. As sessões em que nem
isso existe aparecem marcadas, e o resumo diz quantas são. Medir de verdade exige
o motor passar a gravar — é o passo seguinte.

**Resultado de portão fica de fora.** Hoje ele só existe dentro da captura de
terminal, em texto corrido com códigos de cor. Interpretar aquilo é caro e
frágil. As capturas continuam guardadas como evidência de última instância.

**Custo em dinheiro não é calculado** enquanto ninguém preencher a tabela
`preco_modelo`. Preço é regra de negócio: sem ele cadastrado, o resumo diz que
não sabe, em vez de inventar um número. Tokens continuam contados.

**Nada anterior a 31/08/2026** tem rastro. A esteira só passou a arquivar sessão
a partir dali.

## Duas armadilhas que já custaram tempo

**O tempo em cada status do quadro é recurso pago.** A chamada responde
`TIS_027 — Time In Status is not available on your plan`, e o endereço de
histórico da tarefa não existe mais. O relógio vem dos comentários, que são de
graça e ainda dizem o que aconteceu e quem assinou.

**A base local do repositório envelhece sem avisar.** Atribuir commit a unidade
pelo intervalo `base..branch` parece certo e está errado: com a base atrasada, o
intervalo devolve o trabalho de todas as unidades, e a atribuição fica com quem
rodou por último. A atribuição sai do **merge**, que diz de qual branch veio o
que entrou.
