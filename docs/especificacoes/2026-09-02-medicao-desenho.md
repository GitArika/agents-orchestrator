# Medição da esteira — desenho

Data: 02/09/2026 · Estado: proposto, aguardando revisão humana

## Por que isto existe

A esteira rodou uma corrida inteira e não sabe dizer quanto produziu. Ela deixou rastro
farto — despachos, pastas de sessão arquivadas, transcrições, estado do laço, comentários
no quadro, commits — mas nenhuma dessas seis fontes conversa com as outras, e nenhuma
sozinha responde à pergunta que interessa: **quanto custou e quanto rendeu cada unidade de
trabalho.**

Sem esse número, a esteira só se defende com "funcionou bem aqui", que não convence
ninguém de fora. Com ele, cada corrida vira evidência.

## O que este documento decide

Um armazém de métricas e um coletor, ambos vivendo na máquina onde a esteira roda, que
leem o rastro que já existe — retroativo e contínuo pelo mesmo caminho — e respondem, por
unidade de trabalho: quanto tempo levou, quantas vezes voltou, quanto tempo ficou parada
esperando uma pessoa, quantos tokens consumiu e quanto código produziu.

Não decide nada sobre telas. Exibição é assunto de outro documento, depois de os dados
existirem.

## Onde tudo vive

Tudo na máquina da esteira (o servidor), no usuário que a opera. A máquina de
desenvolvimento não hospeda nem executa nada.

| Coisa | Lugar |
| --- | --- |
| Código | `~/orquestrador` — o próprio repositório do orquestrador, versionado e publicável de lá |
| Executável | `~/orquestrador/bin/orq-medir`, ao lado dos outros quatro |
| Armazém | `~/.claude/orchestrator/state/medicao.db` — dado, portanto fora do repositório |
| História da outra máquina | `~/.claude/orchestrator/historico-mac/` — cópia única, já feita |

O armazém é um arquivo SQLite. **A razão é portabilidade, não preguiça:** o servidor já
traz Python 3.12 com SQLite embutido, então o coletor não acrescenta uma única dependência
— e um medidor que não pede instalação é um medidor que roda na máquina de qualquer
cliente. São centenas de sessões, não milhões; o formato não é o limite.

## As fontes, e o que cada uma sabe

Medido em 02/09/2026, 23h.

| Fonte | O que ela sabe | Servidor | História |
| --- | --- | --- | --- |
| `state/runs.jsonl` | que a sessão **nasceu**: hora, esteira, unidade, tarefa, etapa, branch | 145 | 89 |
| `state/archive/<esteira>/<unidade>-<etapa>-<carimbo>/meta.json` | que a sessão **morreu**, e **como**: desfecho, status final, hora | 151 | 93 |
| `.../<unidade>-<etapa>.events` | ganchos: quando parou, quando pediu atenção | idem | idem |
| `.../*.brief.md` | a ordem de serviço que a sessão recebeu | idem | idem |
| `.../*.log` | a captura do terminal inteiro | idem | idem |
| `~/.claude/projects/*CU-*/*.jsonl` | **tokens por mensagem**, modelo, hora | 15 pastas | 27 pastas, 163 arquivos |
| `state/loop-<esteira>.json` | ciclos do laço, quarentena, **retrabalho por tarefa**, esperas humanas em aberto | ✓ | ✓ |
| `state/notify.log` | avisos entregues, com hora | ✓ | ✓ |
| `state/ram.csv` | consumo real de memória ao longo do tempo | ✓ | — |
| ClickUp (comentários) | **o relógio das transições**, com hora, autor e o commit citado | API | API |
| `~/repos/app-exemplo` | commits por branch da esteira: arquivos, linhas | ✓ | ✓ |
| `.orchestrator/pipeline.toml` | as unidades declaradas, dependências e portões | ✓ | ✓ |

### Duas descobertas que moldaram o desenho

**O tempo em cada status do ClickUp é recurso pago e não está disponível.** A chamada
responde `TIS_027 — Time In Status is not available on your plan`, e o endereço de
histórico da tarefa não existe mais na versão 2 da API. É a mesma família de armadilha do
apontamento de hora.

**Mas os comentários dão o relógio de graça, e melhor.** Cada transição de etapa deixou um
comentário carimbado com hora e autor, e o texto cita o commit: *"Spec publicada"*,
*"entregue no commit 8ae3f26"*, *"REPROVADO (retrabalho 1/2)"*, *"APROVADO"*, *"INTEGRADO E
PUBLICADO"*. É uma fonte melhor que o recurso pago, porque diz também **o que** aconteceu,
não só quando.

## O modelo

```sql
CREATE TABLE maquina (
  id           INTEGER PRIMARY KEY,
  nome         TEXT NOT NULL UNIQUE,   -- 'servidor' | 'historico-mac'
  papel        TEXT NOT NULL           -- 'corrente' | 'historico'
);

CREATE TABLE esteira (
  id             INTEGER PRIMARY KEY,
  nome           TEXT NOT NULL UNIQUE, -- 'Qualidade do Front-end'
  projeto        TEXT,                 -- caminho do repositório do produto
  arquivo_config TEXT
);

CREATE TABLE unidade (
  id           INTEGER PRIMARY KEY,
  esteira_id   INTEGER NOT NULL REFERENCES esteira(id),
  codigo       TEXT NOT NULL,          -- 'FE-01'
  tarefa       TEXT NOT NULL,          -- id no ClickUp
  titulo       TEXT,
  branch       TEXT,
  UNIQUE (esteira_id, codigo)
);

CREATE TABLE sessao (
  id              INTEGER PRIMARY KEY,
  unidade_id      INTEGER NOT NULL REFERENCES unidade(id),
  maquina_id      INTEGER NOT NULL REFERENCES maquina(id),
  etapa           TEXT NOT NULL,       -- spec | implement | review | integrate
  inicio          TEXT,                -- ISO 8601 UTC
  inicio_deduzido INTEGER NOT NULL DEFAULT 0,
  fim             TEXT,
  fim_deduzido    INTEGER NOT NULL DEFAULT 0,
  desfecho        TEXT,                -- normalizado, ver abaixo
  desfecho_bruto  TEXT,                -- como veio, para auditoria
  status_final    TEXT,
  pasta           TEXT,                -- caminho da pasta arquivada, quando houver
  chave           TEXT NOT NULL UNIQUE -- identidade natural, ver "Reexecução segura"
);

CREATE TABLE consumo (
  id                   INTEGER PRIMARY KEY,
  sessao_id            INTEGER REFERENCES sessao(id),
  unidade_id           INTEGER NOT NULL REFERENCES unidade(id),
  transcricao          TEXT NOT NULL,  -- caminho do arquivo
  modelo               TEXT NOT NULL,
  mensagens            INTEGER NOT NULL,
  tokens_entrada       INTEGER NOT NULL,
  tokens_saida         INTEGER NOT NULL,
  tokens_cache_leitura INTEGER NOT NULL,
  tokens_cache_escrita INTEGER NOT NULL,
  primeiro_ts          TEXT,
  ultimo_ts            TEXT,
  UNIQUE (transcricao, modelo)
);

CREATE TABLE evento (
  id         INTEGER PRIMARY KEY,
  unidade_id INTEGER REFERENCES unidade(id),
  sessao_id  INTEGER REFERENCES sessao(id),
  maquina_id INTEGER REFERENCES maquina(id),
  ts         TEXT NOT NULL,
  origem     TEXT NOT NULL,   -- despacho | gancho | aviso | comentario | commit | laco
  tipo       TEXT NOT NULL,
  autor      TEXT,
  texto      TEXT,
  chave      TEXT NOT NULL UNIQUE   -- identidade natural, para reexecução segura
);

CREATE TABLE commit_unidade (
  sha        TEXT PRIMARY KEY,
  unidade_id INTEGER REFERENCES unidade(id),
  ts         TEXT NOT NULL,
  arquivos   INTEGER,
  insercoes  INTEGER,
  delecoes   INTEGER,
  mensagem   TEXT
);

CREATE TABLE preco_modelo (
  modelo                    TEXT NOT NULL,
  vigencia_inicio           TEXT NOT NULL,
  moeda                     TEXT NOT NULL,
  entrada_por_milhao        REAL NOT NULL,
  saida_por_milhao          REAL NOT NULL,
  cache_leitura_por_milhao  REAL NOT NULL,
  cache_escrita_por_milhao  REAL NOT NULL,
  PRIMARY KEY (modelo, vigencia_inicio)
);
```

**A tabela de preço nasce vazia, de propósito.** Preço é regra de negócio: enquanto
ninguém a preencher, o custo em dinheiro aparece como desconhecido, nunca como número
inventado. Tokens continuam contados normalmente.

## Como o desfecho é normalizado

O motor grava o desfecho em texto livre. O coletor guarda o original e normaliza:

| Como vem | Vira | Significa |
| --- | --- | --- |
| `advanced:<etapa>` | `avancou` | a unidade passou para a etapa seguinte |
| `hold` | `travou` | parou esperando uma pessoa |
| `rejected-><etapa>` | `reprovou` | voltou para trás com achados |
| `reset` | `reiniciou` | devolvida à fila |
| `loop-reset:<n>` | `orfa` | a sessão morreu sem se despedir e o laço recolheu |

Distribuição na história já copiada, para conferência do coletor: 27 `avancou` de
especificação, 21 de implementação, 13 de revisão, 14 de integração; 9 `travou`,
7 `reprovou`, 1 `reiniciou`, 1 `orfa`.

## O coletor

Um executável, `orq-medir`, com três verbos:

| Verbo | O que faz |
| --- | --- |
| `orq-medir esquema` | cria ou atualiza o armazém |
| `orq-medir coletar` | varre todas as fontes e preenche; seguro repetir |
| `orq-medir resumo` | imprime os números principais na tela |

### A ordem da varredura

1. **Pastas de sessão arquivadas** — são a autoridade sobre desfecho. Cada pasta vira uma
   sessão. O carimbo no nome da pasta é hora local de arquivamento; o campo `archived_at`
   é a mesma hora em UTC e é ele que vale.
2. **Registro de despachos** — dá o início. O casamento é por esteira, unidade e etapa, em
   ordem cronológica: o despacho válido é o mais recente antes do arquivamento que ainda
   não foi consumido por outra sessão. Isso importa porque unidades repetem — uma delas
   teve quatro implementações.
3. **Sobras dos dois lados são registradas, não descartadas.** No servidor há mais pastas
   arquivadas que despachos; sessão sem despacho fica com início deduzido e marcado,
   despacho sem pasta vira sessão sem desfecho. Rastro incompleto é informação, e some se
   for jogado fora.
4. **Transcrições** — o caminho da pasta contém o branch, e o branch contém o id da tarefa.
   A transcrição pertence à sessão daquela tarefa cuja janela de tempo contém o primeiro
   carimbo dela. Sem janela correspondente, fica ligada à unidade e não à sessão.
5. **Estado do laço** — retrabalho por tarefa, quarentena e esperas humanas em aberto.
6. **Avisos e ganchos** — viram eventos.
7. **Comentários do ClickUp** — viram eventos com autor e hora, e os commits citados no
   texto são extraídos.
8. **Git do produto** — para cada branch da esteira, os commits com arquivos e linhas.

### Reexecução segura

Toda linha tem identidade natural e é gravada por acréscimo com substituição. Rodar o
coletor dez vezes seguidas produz o mesmo armazém que rodar uma vez. É isso que permite ao
mesmo código servir para o retroativo e para o contínuo.

**A identidade da sessão é um campo explícito, não uma combinação de colunas.** A primeira
versão deste desenho identificava a sessão por unidade, etapa, início e máquina — e isso
estaria errado: sessão recolhida sem despacho não tem início, e coluna vazia não conta como
repetida na comparação, então duas execuções do coletor criariam duas linhas para a mesma
sessão. A chave é montada pelo coletor a partir da máquina, da esteira, da unidade, da etapa
e do carimbo do arquivamento — ou do despacho, quando não houver arquivamento — e nunca é
vazia.

Sessão que tem despacho e não tem pasta arquivada fica com fim e desfecho vazios: é uma
sessão que nasceu e cujo fim não foi registrado, e isso é um fato sobre a esteira, não um
buraco a preencher.

### Convivência com a esteira viva

O coletor **só lê pastas já arquivadas e transcrições de sessões encerradas**, nunca toca
no que está em curso, e escreve exclusivamente no próprio armazém. Roda em prioridade
baixa de processador e de disco. Ele não disputa memória com as sessões.

## As vistas

| Vista | Responde |
| --- | --- |
| `v_ciclo_por_unidade` | quanto tempo da primeira especificação até a integração, e quanto em cada etapa |
| `v_retrabalho` | quantas vezes cada unidade voltou, e de qual etapa |
| `v_espera_humana` | quanto tempo a unidade ficou parada esperando uma pessoa, e por quê |
| `v_consumo_por_unidade` | tokens por modelo, e dinheiro quando houver preço |
| `v_producao_por_unidade` | commits, arquivos e linhas |

## A automação

Um temporizador do próprio sistema, no usuário da esteira, de hora em hora. A permanência
de sessão já está ligada no servidor, então ele roda sem ninguém conectado. Prioridade
baixa. O registro de cada execução fica no diário do sistema.

## Como isto se prova

O coletor é função pura sobre arquivos, então o teste é material congelado com resultado
afirmado. Três pastas de sessão reais viram material fixo:

- uma que avançou normalmente;
- uma que travou pedindo decisão humana;
- uma que morreu sem se despedir.

Mais um caso montado para o casamento entre despacho e arquivo, usando a unidade que teve
quatro implementações — é exatamente ali que esse tipo de código erra, associando a sessão
ao despacho errado.

**Efeito colateral desejado:** esta é a primeira bateria de testes de verdade do motor do
orquestrador, que hoje só tem prova nas funções de leitura de memória e na cerca.

## Limites conhecidos, ditos agora

- **Duração de sessão é deduzida**, não medida, até o motor passar a gravar início e fim.
  Toda linha deduzida vem marcada como tal, e nenhuma conta mistura medido com deduzido sem
  avisar.
- **Resultado de portão fica de fora nesta entrega.** Ele existe hoje só dentro da captura
  de terminal, em texto corrido com códigos de cor. Interpretar aquilo é caro e frágil; o
  caminho certo é o motor gravar em campo próprio. As capturas ficam indexadas — onde
  estão, de que sessão, tamanho — para servir de evidência de última instância.
- **Custo em dinheiro só aparece depois** de alguém preencher a tabela de preço.
- **Nada anterior a 31/08/2026** tem rastro: a esteira só passou a arquivar sessão a partir
  dali.
- **Sessões fora da esteira não entram.** Decisão do dono: o escopo é a esteira.

## Fora de escopo

Telas, painéis e relatórios. Emissão de eventos pelo motor (é o passo seguinte, depois de
sabermos exatamente quais campos faltam). Qualquer outra ferramenta de gestão além do
ClickUp.
