# OA-01 — Núcleo de estado em SQLite

**Prioridade:** P0 · **Depende de:** nada · **Bloqueia:** OA-02, OA-03, OA-13

## Por que existe

Hoje o estado da esteira mora em três lugares que ninguém coordena: o `pipeline.toml`
versionado (grafo), o ClickUp (status) e o `state/loop-<esteira>.json` (strikes, quarentena,
bloqueios). O terceiro é lido e regravado sem nenhum lock — `tick()` lê o arquivo em
[bin/orq:2202](../../../bin/orq:2202), gasta segundos ou minutos em rede e lançamento de
sessões, e só então grava em [bin/orq:2352](../../../bin/orq:2352), sobrescrevendo qualquer
bloqueio que uma sessão tenha registrado no meio. `save_loop_state` usa `write_text`, que
trunca antes de escrever: uma queda no meio deixa JSON inválido, e `loop_state` engole a
exceção e devolve estado vazio — quarentena, bloqueios e contadores somem em silêncio.

Esta unidade substitui os três por um banco SQLite por esteira, fora do repositório, com
transação de verdade. É a raiz de toda a entrega: nada mais começa antes dela.

## Escopo

**Dentro:** esquema, camada de acesso, disciplina de transação, versionamento de esquema,
localização do arquivo, bateria de concorrência.

**Fora:** os verbos de linha de comando (OA-02), a máquina de estados (OA-03), qualquer
remoção de código antigo (OA-04).

## Desenho

### Onde mora

```
~/.config/orquestrador/esteiras/<nome-da-esteira>.db
```

Um arquivo por esteira, decidido em 21/09/2026: esteira travada não segura a outra, e o
descarte é por esteira. O diretório já é a convenção do resolvedor atual
([bin/orq:408](../../../bin/orq:408)). Permissão `600` — o banco carrega id de tarefa e
caminho de repositório, não credencial, mas o arquivo é pessoal.

Resolução, na ordem: `--db <caminho>` → `$ORQ_DB` → `~/.config/orquestrador/esteiras/*.db`
cujo `repo` casa com o repositório onde você está → o último usado. É a mesma regra que
`find_config` já aplica ao TOML ([bin/orq:443](../../../bin/orq:443)), com a checagem de
máquina de [bin/orq:330](../../../bin/orq:330) preservada: banco de outra máquina pode ser
LIDO, nunca escrito por comando implícito.

### Esquema

```sql
PRAGMA journal_mode = WAL;      -- leitores não bloqueiam o escritor
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 10000;    -- 10s: a fila é o kernel esperando, não erro

CREATE TABLE esquema (versao INTEGER NOT NULL);

CREATE TABLE config (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

CREATE TABLE unidade (
  id           INTEGER PRIMARY KEY,
  chave        TEXT NOT NULL UNIQUE,          -- FE-01
  clickup_id   TEXT UNIQUE,                   -- 868xxxxxx
  titulo       TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'backlog'
               CHECK (status IN ('backlog','em_progresso','revisao','pronto','bloqueado')),
  motivo       TEXT DEFAULT '',               -- por que está bloqueada
  modo         TEXT NOT NULL DEFAULT 'autonomous',
  prioridade   INTEGER NOT NULL DEFAULT 2,    -- 0 urgente … 4 sem
  branch       TEXT,
  pr_numero    INTEGER,
  pr_url       TEXT,
  strikes      INTEGER NOT NULL DEFAULT 0,
  retrabalho   INTEGER NOT NULL DEFAULT 0,
  criado_em    TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);

CREATE TABLE dependencia (
  unidade_id   INTEGER NOT NULL REFERENCES unidade(id) ON DELETE CASCADE,
  depende_de   INTEGER NOT NULL REFERENCES unidade(id) ON DELETE CASCADE,
  PRIMARY KEY (unidade_id, depende_de),
  CHECK (unidade_id <> depende_de)
);

CREATE TABLE portao (
  id      INTEGER PRIMARY KEY,
  tipo    TEXT NOT NULL CHECK (tipo IN ('setup','verify','teardown')),
  ordem   INTEGER NOT NULL,
  comando TEXT NOT NULL
);

CREATE TABLE evento (                          -- append-only; o rastro
  id         INTEGER PRIMARY KEY,
  unidade_id INTEGER REFERENCES unidade(id) ON DELETE SET NULL,
  tipo       TEXT NOT NULL,                    -- despachada, pr_aberto, bloqueada, …
  de_status  TEXT, para_status TEXT,
  texto      TEXT NOT NULL DEFAULT '',
  ts         TEXT NOT NULL
);

CREATE TABLE sessao (
  id           INTEGER PRIMARY KEY,
  unidade_id   INTEGER NOT NULL REFERENCES unidade(id) ON DELETE CASCADE,
  tmux         TEXT, pid INTEGER,
  worktree     TEXT NOT NULL, branch TEXT NOT NULL,
  iniciada_em  TEXT NOT NULL, encerrada_em TEXT,
  desfecho     TEXT
);
```

`config` guarda o que vivia em `[pipeline]`, `[session]` e `[loop]`: `name`, `repo`,
`base_branch`, `work_dir`, `worktree_root`, `branch_template`, `list_id`, `github_repo`,
`max_concurrent`, `reserve_ram_gb`, `ram_per_session_gb`, `interval_seconds`, `max_strikes`,
`max_rework`, `permission_mode`, `remote_control`, `model`, `verificacao_automatica`.

### A disciplina que faz a fila existir

Um único ponto de escrita, e ele é o contrato:

```python
@contextmanager
def transacao(db):                 # BEGIN IMMEDIATE já na entrada
    con = conectar(db)             # PRAGMAs aplicados a cada conexão
    con.execute("BEGIN IMMEDIATE") # pega o lock de escrita AGORA, não na 1ª escrita
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
```

Três regras não negociáveis:

1. **Nenhum `UPDATE` fora de `transacao`.** Ler-modificar-gravar entre duas conexões é
   exatamente a falha que esta unidade existe para matar.
2. **Toda transição de status grava um `evento` na MESMA transação.** Rastro que pode
   divergir do estado não é rastro.
3. **`BEGIN IMMEDIATE`, nunca o `BEGIN` implícito.** Com o implícito, dois escritores só
   descobrem o conflito no commit e um leva `SQLITE_BUSY` depois de já ter trabalhado.

`busy_timeout` é o enfileiramento pedido no requisito: quem chega segundo espera no kernel
até 10s em vez de falhar. Leitura nunca espera — é o que o WAL entrega de graça.

### Versionamento de esquema

`esquema.versao` começa em 1. A abertura compara com a versão que o binário conhece:
menor → aplica as migrações em ordem, dentro de uma transação; maior → recusa com a
mensagem de qual binário é mais novo. Banco sem a tabela é banco de versão desconhecida:
recusa, não adivinha.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| O banco nasce com WAL, chaves estrangeiras e timeout | `sqlite3 <db> 'PRAGMA journal_mode; PRAGMA foreign_keys;'` → `wal`, `1` |
| Escrita concorrente não perde atualização | Teste: 20 processos gravando transições na mesma unidade; ao fim, `SELECT count(*) FROM evento` = 20 e o status final é o da última transição válida |
| Escrita interrompida não corrompe | Teste: `kill -9` no meio de uma transação; a abertura seguinte lê o estado anterior íntegro |
| Estado nunca volta vazio em silêncio | Banco ilegível **recusa com erro**; nenhum caminho devolve defaults (contraste com [bin/orq:2128](../../../bin/orq:2128)) |
| Dependência não aceita ciclo | `orq dep add A --needs B` depois `B --needs A` → recusa com o caminho do ciclo |
| Toda transição deixa evento | Teste: após N transições, `count(evento) >= N` e cada uma tem `de_status`/`para_status` |

## Riscos

- **WAL exige sistema de arquivos local.** Em `~/.config` isso vale; num diretório montado
  por rede, não. O pré-voo (OA-12) precisa provar.
- **O banco deixa de ser revisável em PR.** É a perda consciente de tirar a declaração do
  repositório. Mitigação mínima: `orq export` (OA-02) produz texto estável e difável, e a
  tabela `evento` é append-only.
