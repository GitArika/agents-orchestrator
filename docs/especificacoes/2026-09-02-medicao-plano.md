# Medição da esteira — plano de implementação

> **Para quem executa:** cada passo é uma ação de 2 a 5 minutos, com teste antes da
> implementação. As caixas marcam progresso.

**Objetivo:** dar à esteira um armazém que responda, por unidade de trabalho, quanto tempo
levou, quantas vezes voltou, quanto esperou por uma pessoa, quantos tokens consumiu e
quanto código produziu.

**Arquitetura:** um executável em Python puro (`bin/orq-medir`) que lê o rastro já existente
de oito fontes e preenche um arquivo SQLite. O mesmo código faz o retroativo e o contínuo,
porque toda gravação tem identidade natural e é idempotente.

**Ferramentas:** Python 3.12 da casa, biblioteca padrão apenas.

**Desenho:** `docs/especificacoes/2026-09-02-medicao-desenho.md`

## Restrições globais

Valem para todas as tarefas.

- **Nenhuma dependência nova.** Só biblioteca padrão: `sqlite3`, `json`, `pathlib`,
  `urllib`, `subprocess`, `tomllib`, `datetime`, `re`, `os`.
- **O executável não tem extensão** e mora em `bin/`, como os outros quatro. Os testes o
  carregam com `importlib.machinery.SourceFileLoader`, como `testes/test_orq.py` já faz.
- **Testes em `unittest`**, arquivo `testes/test_medicao.py`, executável por
  `python3 testes/test_medicao.py`.
- **Identificadores em português**, como o resto do repositório.
- **O coletor só lê.** Escreve exclusivamente em `medicao.db`. Nunca toca em `runs.jsonl`,
  no estado do laço, nas pastas de sessão ou nas transcrições.
- **Só lê o que está encerrado:** pastas já arquivadas e transcrições de sessões que
  terminaram. Nada em curso.
- **Nenhum valor de domínio no código.** Preço de modelo vive na tabela `preco_modelo`, que
  nasce vazia; sem preço, o custo em dinheiro é desconhecido, nunca zero nem estimado.
- **Todo carimbo de tempo é ISO 8601 em UTC**, com `Z` no fim.
- **Material de teste é aparado:** as pastas de sessão reais copiadas para `testes/material/`
  levam apenas `meta.json` e `.events`. As capturas de terminal (centenas de KB cada) e as
  ordens de serviço ficam de fora — não são lidas por nenhuma função testada.

---

## Tarefa 1: Esquema e identidade

**Arquivos:**
- Criar: `bin/orq-medir`
- Criar: `testes/test_medicao.py`

**Interfaces:**
- Produz: `abrir(caminho) -> sqlite3.Connection` (cria o esquema se faltar, idempotente);
  `chave_sessao(maquina, esteira, unidade, etapa, carimbo) -> str`

- [ ] **Passo 1: escrever o teste que falha**

```python
class Esquema(unittest.TestCase):
    def test_cria_e_repete_sem_erro(self):
        with tempfile.TemporaryDirectory() as d:
            alvo = pathlib.Path(d) / "m.db"
            medir.abrir(alvo).close()
            medir.abrir(alvo).close()          # segunda vez não pode explodir
            con = sqlite3.connect(alvo)
            nomes = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            for t in ("maquina", "esteira", "unidade", "sessao", "consumo",
                      "evento", "commit_unidade", "preco_modelo"):
                self.assertIn(t, nomes)

class ChaveDeSessao(unittest.TestCase):
    def test_estavel_e_nunca_vazia(self):
        a = medir.chave_sessao("servidor", "Q", "FE-01", "spec", "2026-08-31T16:45:17Z")
        b = medir.chave_sessao("servidor", "Q", "FE-01", "spec", "2026-08-31T16:45:17Z")
        self.assertEqual(a, b)
        self.assertTrue(a)

    def test_distingue_repeticoes_da_mesma_etapa(self):
        # FE-14 teve quatro implementações; elas não podem colidir.
        a = medir.chave_sessao("servidor", "Q", "FE-14", "implement", "2026-08-31T22:01:49Z")
        b = medir.chave_sessao("servidor", "Q", "FE-14", "implement", "2026-09-01T02:47:29Z")
        self.assertNotEqual(a, b)
```

- [ ] **Passo 2: rodar e ver falhar**

`python3 testes/test_medicao.py` → falha ao carregar `bin/orq-medir` (não existe).

- [ ] **Passo 3: implementar o mínimo**

`bin/orq-medir` com o cabeçalho `#!/usr/bin/env python3`, o DDL das sete tabelas e da
tabela de preço exatamente como está no desenho, mais:

```python
def chave_sessao(maquina, esteira, unidade, etapa, carimbo):
    return "|".join((maquina, esteira, unidade, etapa, carimbo))

def abrir(caminho):
    con = sqlite3.connect(caminho)
    con.executescript(DDL)          # todo CREATE com IF NOT EXISTS
    return con
```

- [ ] **Passo 4: rodar e ver passar**

- [ ] **Passo 5: commitar**

```bash
git add bin/orq-medir testes/test_medicao.py
git commit -m "feat(medicao): esquema do armazém e identidade da sessão"
```

---

## Tarefa 2: As sessões

O coração. Ao fim dela, `orq-medir` já responde quantas sessões houve e como terminaram.

**Arquivos:**
- Modificar: `bin/orq-medir`
- Modificar: `testes/test_medicao.py`
- Criar: `testes/material/` com três pastas de sessão reais, aparadas

**Interfaces:**
- Consome: `abrir`, `chave_sessao`
- Produz: `normalizar_desfecho(bruto) -> str`; `sessoes_arquivadas(raiz) -> list[dict]`;
  `despachos(caminho_jsonl) -> list[dict]`; `casar(sessoes, despachos) -> list[dict]`

- [ ] **Passo 1: escrever os testes que falham**

```python
class Desfecho(unittest.TestCase):
    def test_traducao(self):
        self.assertEqual(medir.normalizar_desfecho("advanced:review"), "avancou")
        self.assertEqual(medir.normalizar_desfecho("hold"), "travou")
        self.assertEqual(medir.normalizar_desfecho("rejected->implement"), "reprovou")
        self.assertEqual(medir.normalizar_desfecho("reset"), "reiniciou")
        self.assertEqual(medir.normalizar_desfecho("loop-reset:1"), "orfa")

    def test_desconhecido_nao_vira_palpite(self):
        self.assertIsNone(medir.normalizar_desfecho("coisa-nova"))

class SessoesArquivadas(unittest.TestCase):
    def test_le_as_tres_do_material(self):
        s = medir.sessoes_arquivadas(MATERIAL)
        por_desfecho = {x["desfecho"] for x in s}
        self.assertEqual(por_desfecho, {"avancou", "travou", "orfa"})
        for x in s:
            self.assertTrue(x["fim"].endswith("Z"))
            self.assertTrue(x["unidade"] and x["etapa"] and x["tarefa"])

class Casamento(unittest.TestCase):
    """Onde este tipo de código erra: quatro implementações da mesma unidade."""
    SESSOES = [
        {"unidade": "FE-14", "etapa": "implement", "fim": "2026-08-31T22:10:00Z"},
        {"unidade": "FE-14", "etapa": "implement", "fim": "2026-09-01T02:55:00Z"},
    ]
    DESPACHOS = [
        {"unit": "FE-14", "stage": "implement", "ts": "2026-08-31T22:01:49Z"},
        {"unit": "FE-14", "stage": "implement", "ts": "2026-09-01T02:47:29Z"},
        {"unit": "FE-14", "stage": "implement", "ts": "2026-09-01T09:00:00Z"},  # sem par
    ]

    def test_cada_sessao_pega_o_despacho_anterior_mais_proximo(self):
        r = medir.casar(self.SESSOES, self.DESPACHOS)
        self.assertEqual(r[0]["inicio"], "2026-08-31T22:01:49Z")
        self.assertEqual(r[1]["inicio"], "2026-09-01T02:47:29Z")
        self.assertFalse(r[0]["inicio_deduzido"])

    def test_despacho_sem_sessao_vira_sessao_sem_fim(self):
        r = medir.casar(self.SESSOES, self.DESPACHOS)
        soltas = [x for x in r if x.get("fim") is None]
        self.assertEqual(len(soltas), 1)
        self.assertEqual(soltas[0]["inicio"], "2026-09-01T09:00:00Z")
        self.assertIsNone(soltas[0]["desfecho"])

    def test_sessao_sem_despacho_tem_inicio_deduzido_e_marcado(self):
        r = medir.casar(self.SESSOES[:1], [])
        self.assertTrue(r[0]["inicio_deduzido"])
```

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: montar o material de teste**

Copiar três pastas reais de `~/.claude/orchestrator/historico-mac/state/archive/qualidade-do-front-end/`
para `testes/material/`, levando **apenas** `meta.json` e o arquivo `.events`:

- `FE-01-integrate-20260831-182456` — desfecho `advanced:integrate`
- `DS-02-implement-20260901-004411` — desfecho `hold`
- `DS-02-implement-20260831-234828` — desfecho `loop-reset:1` (morreu sem se despedir)

- [ ] **Passo 4: implementar**

`normalizar_desfecho` por prefixo, devolvendo `None` para o que não conhece — desfecho novo
não pode virar palpite silencioso.

`sessoes_arquivadas` varre `<raiz>/<esteira>/<unidade>-<etapa>-<carimbo>/meta.json` e usa
`archived_at` como fim (o carimbo do nome da pasta é hora local; o campo é UTC e é o que
vale).

`casar` ordena os dois lados por tempo e percorre por (unidade, etapa): cada sessão toma o
despacho mais recente ainda livre anterior ao seu fim. Sessão sem despacho fica com
`inicio_deduzido=True` e início igual ao fim. Despacho que sobra vira sessão com `fim` e
`desfecho` vazios.

- [ ] **Passo 5: rodar e ver passar**

- [ ] **Passo 6: ligar ao armazém e provar com dado real**

`orq-medir coletar` grava sessões; `orq-medir resumo` imprime a contagem por desfecho.
Rodar sobre a história copiada e conferir contra o desenho: 27+21+13+14 avançadas,
9 travadas, 7 reprovadas, 1 reiniciada, 1 órfã.

- [ ] **Passo 7: rodar duas vezes e provar que não duplica**

- [ ] **Passo 8: commitar**

---

## Tarefa 3: O consumo

**Arquivos:** modificar `bin/orq-medir`, `testes/test_medicao.py`; criar
`testes/material/transcricao-curta.jsonl`

**Interfaces:**
- Produz: `tarefa_do_branch(branch) -> str | None`; `consumo_de_transcricao(caminho) -> list[dict]`

- [ ] **Passo 1: escrever o teste que falha**

```python
class TarefaDoBranch(unittest.TestCase):
    def test_extrai_o_id(self):
        self.assertEqual(
            medir.tarefa_do_branch("CU-868kyu9v4-ligar-o-otimizador-automatic"),
            "868kyu9v4")

    def test_branch_de_fora_da_esteira(self):
        self.assertIsNone(medir.tarefa_do_branch("homol"))

class Consumo(unittest.TestCase):
    def test_soma_por_modelo(self):
        linhas = medir.consumo_de_transcricao(MATERIAL / "transcricao-curta.jsonl")
        por_modelo = {l["modelo"]: l for l in linhas}
        self.assertIn("claude-opus-5", por_modelo)
        c = por_modelo["claude-opus-5"]
        self.assertEqual(c["mensagens"], 2)
        self.assertEqual(c["tokens_saida"], 30)
        self.assertEqual(c["tokens_cache_leitura"], 300)
        self.assertEqual(c["tarefa"], "868kyu9v4")
        self.assertTrue(c["primeiro_ts"] <= c["ultimo_ts"])

    def test_linha_corrompida_nao_derruba_a_leitura(self):
        # transcrição em curso pode terminar no meio de uma linha
        linhas = medir.consumo_de_transcricao(MATERIAL / "transcricao-curta.jsonl")
        self.assertTrue(linhas)
```

- [ ] **Passo 2: rodar e ver falhar**

- [ ] **Passo 3: montar o material**

`testes/material/transcricao-curta.jsonl` com quatro linhas: duas mensagens do assistente
com `usage` (saída 10 e 20; leitura de cache 100 e 200), uma linha sem `usage`, e uma
última linha truncada no meio. Todas com `gitBranch` de `CU-868kyu9v4-...`.

- [ ] **Passo 4: implementar**

Ler linha a linha, ignorando o que não decodifica. Agrupar por modelo. `gitBranch` dá a
tarefa; se faltar, cair para o `cwd`.

- [ ] **Passo 5: rodar e ver passar**

- [ ] **Passo 6: ligar à sessão**

A transcrição pertence à sessão da mesma tarefa cuja janela de tempo contém o primeiro
carimbo dela. Sem janela, fica ligada só à unidade.

- [ ] **Passo 7: commitar**

---

## Tarefa 4: Os eventos de dentro

**Arquivos:** modificar `bin/orq-medir`, `testes/test_medicao.py`

**Interfaces:**
- Produz: `eventos_do_laco(caminho_json, esteira) -> list[dict]`;
  `eventos_de_aviso(caminho_log) -> list[dict]`; `eventos_de_gancho(caminho_events) -> list[dict]`

- [ ] **Passo 1: escrever o teste que falha**

```python
class EventosDoLaco(unittest.TestCase):
    ESTADO = {
        "ticks": 366, "dispatched": 85,
        "quarantine": ["868kyu8ec"],
        "rework": {"868kyu71z": 1, "868kyu8ec": 2},
        "hold": {"868kyugea": {"reason": "falta decidir a altura do botão",
                               "at": "2026-09-01T03:44:10Z", "status": "em progresso"}},
    }

    def test_retrabalho_vira_evento_por_tarefa(self):
        ev = medir.eventos_do_laco_dict(self.ESTADO, "Q")
        r = [e for e in ev if e["tipo"] == "retrabalho"]
        self.assertEqual({e["tarefa"] for e in r}, {"868kyu71z", "868kyu8ec"})

    def test_espera_humana_carrega_hora_e_motivo(self):
        ev = medir.eventos_do_laco_dict(self.ESTADO, "Q")
        h = [e for e in ev if e["tipo"] == "espera_humana"][0]
        self.assertEqual(h["ts"], "2026-09-01T03:44:10Z")
        self.assertIn("altura do botão", h["texto"])

    def test_quarentena(self):
        ev = medir.eventos_do_laco_dict(self.ESTADO, "Q")
        self.assertTrue([e for e in ev if e["tipo"] == "quarentena"])

class EventosDeGancho(unittest.TestCase):
    LINHAS = ("2026-09-01T02:32:08Z\tstop\tConfira o board: orq status\n"
              "2026-09-01T02:33:08Z\tnotification\tClaude is waiting for your input\n")

    def test_le_hora_tipo_e_texto(self):
        ev = medir.eventos_de_gancho_texto(self.LINHAS)
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0]["tipo"], "stop")
        self.assertEqual(ev[1]["ts"], "2026-09-01T02:33:08Z")
```

- [ ] **Passo 2: rodar e ver falhar**
- [ ] **Passo 3: implementar** — funções puras sobre dicionário e texto; as que leem arquivo
      são casca fina sobre elas, para o teste não precisar de disco.
- [ ] **Passo 4: rodar e ver passar**
- [ ] **Passo 5: gravar com chave natural e provar que repetir não duplica**
- [ ] **Passo 6: commitar**

---

## Tarefa 5: Os eventos de fora

**Arquivos:** modificar `bin/orq-medir`, `testes/test_medicao.py`

**Interfaces:**
- Produz: `eventos_de_comentarios(payload, tarefa) -> list[dict]`;
  `commits_da_unidade(repo, branch) -> list[dict]`

- [ ] **Passo 1: escrever o teste que falha**

```python
class Comentarios(unittest.TestCase):
    PAYLOAD = {"comments": [
        {"id": "1", "date": "1788211481689",
         "user": {"username": "Ariel Evangelista", "id": 1},
         "comment_text": "INTEGRADO E PUBLICADO. merge-base ae43e34, commit c461c71."},
        {"id": "2", "date": "1788200000000",
         "user": {"username": "Ariel Evangelista", "id": 1},
         "comment_text": "REPROVADO (retrabalho 1/2) — volta para 'spec pronta'."},
    ]}

    def test_hora_em_utc_e_autor(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z")
        self.assertTrue(all(e["ts"].endswith("Z") for e in ev))
        self.assertEqual(ev[0]["autor"], "Ariel Evangelista")

    def test_classifica_a_transicao(self):
        ev = {e["tipo"] for e in medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z")}
        self.assertIn("integrado", ev)
        self.assertIn("reprovado", ev)

    def test_extrai_commits_citados(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z")
        shas = {s for e in ev for s in e["commits"]}
        self.assertIn("c461c71", shas)
        self.assertIn("ae43e34", shas)
```

- [ ] **Passo 2: rodar e ver falhar**
- [ ] **Passo 3: implementar** — data em milissegundos vira UTC; classificação por marcador
      no começo do texto (`REPROVADO`, `APROVADO`, `INTEGRADO`, `entregue no commit`,
      `Spec publicada`), caindo para `comentario` quando não reconhece; commits por expressão
      de sete a quarenta caracteres hexadecimais conferida contra o repositório.
- [ ] **Passo 4: rodar e ver passar**
- [ ] **Passo 5: buscar de verdade** — uma chamada por tarefa, guardando o payload; a
      credencial sai de `~/.env.clickup`, e a leitura é a única parte que usa rede.
- [ ] **Passo 6: commits por branch** — `git log --numstat` sobre cada branch da esteira no
      repositório do produto, gravando arquivos, inserções e deleções.
- [ ] **Passo 7: commitar**

---

## Tarefa 6: As unidades, as vistas e o resumo

**Arquivos:** modificar `bin/orq-medir`, `testes/test_medicao.py`

**Interfaces:**
- Produz: `unidades_do_pipeline(caminho_toml) -> list[dict]`

- [ ] **Passo 1: escrever o teste que falha**

```python
class UnidadesDeclaradas(unittest.TestCase):
    TOML = b"""
[[task]]
id = "868kyu71z"
key = "FE-01"
title = "Erro numa tela nao pode apagar o aplicativo inteiro"
depends_on = []
mode = "autonomous"
"""

    def test_le_codigo_tarefa_e_titulo(self):
        u = medir.unidades_do_toml(tomllib.loads(self.TOML.decode()))
        self.assertEqual(u[0]["codigo"], "FE-01")
        self.assertEqual(u[0]["tarefa"], "868kyu71z")
        self.assertIn("Erro numa tela", u[0]["titulo"])
```

- [ ] **Passo 2: rodar e ver falhar**
- [ ] **Passo 3: implementar** e enriquecer as unidades já criadas pelas sessões com o título
      declarado.
- [ ] **Passo 4: criar as cinco vistas** do desenho.
- [ ] **Passo 5: `orq-medir resumo`** imprime, em português: unidades, sessões por desfecho,
      retrabalho, espera humana acumulada, tokens por modelo, custo (ou "preço não
      cadastrado"), commits e linhas.
- [ ] **Passo 6: rodar sobre o dado real e conferir os números** contra o desenho.
- [ ] **Passo 7: commitar**

---

## Tarefa 7: A automação e a documentação

**Arquivos:** criar `modelos/orq-medir.service`, `modelos/orq-medir.timer`,
`docs/medicao.md`; modificar `README.md`, `instalar.sh`

- [ ] **Passo 1: escrever a unidade e o temporizador** — de hora em hora, `Nice=19`,
      `IOSchedulingClass=idle`, no usuário da esteira.
- [ ] **Passo 2: instalar e provar** que dispara com ninguém conectado, e que a segunda
      execução não muda contagem nenhuma.
- [ ] **Passo 3: `docs/medicao.md`** — o que é medido, o que não é, como ler o resumo, e os
      limites (duração deduzida, portões de fora, preço vazio).
- [ ] **Passo 4: acrescentar o quinto executável** à tabela do `README.md` e ao instalador.
- [ ] **Passo 5: acrescentar o aprendizado nº 21** — o tempo em cada status do ClickUp é
      recurso pago e responde `TIS_027`; os comentários das tarefas são a fonte melhor.
- [ ] **Passo 6: commitar**

---

## Conferência do plano contra o desenho

| O desenho pede | Onde está |
| --- | --- |
| Sete tabelas e a de preço | Tarefa 1 |
| Normalização de desfecho | Tarefa 2 |
| Casamento despacho ↔ arquivo, com repetições | Tarefa 2 |
| Sobras dos dois lados registradas | Tarefa 2 |
| Tokens por modelo, ligados à sessão | Tarefa 3 |
| Retrabalho, quarentena, espera humana | Tarefa 4 |
| Avisos e ganchos | Tarefa 4 |
| Comentários do ClickUp com autor, hora e commit | Tarefa 5 |
| Commits com arquivos e linhas | Tarefa 5 |
| Unidades declaradas | Tarefa 6 |
| As cinco vistas | Tarefa 6 |
| Reexecução segura | Tarefas 2, 4 e 7 |
| Prioridade baixa, sem disputar com a esteira | Tarefa 7 |
| Material de teste com os três desfechos e a repetição | Tarefas 2 e 3 |
