# Medição

A esteira rodou uma corrida inteira e não sabia dizer quanto produziu. O rastro
existia — em seis lugares que não conversavam. Isto junta.

## Os três comandos

```bash
orq-medir esquema     # cria ou atualiza o armazém
orq-medir coletar     # varre tudo e preenche; seguro repetir à vontade
orq-medir resumo      # os números na tela
```

Comece pelo `resumo`. Ele responde "o que esta esteira produziu até agora".

`coletar --sem-rede` pula a consulta ao quadro, quando você quiser rodar sem
internet ou sem gastar chamada.

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

Um temporizador do sistema roda de hora em hora, em prioridade baixa:

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
