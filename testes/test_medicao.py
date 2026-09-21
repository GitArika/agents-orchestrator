"""Testes do medidor da esteira.

O medidor é função pura sobre arquivos, então tudo aqui é material congelado com
resultado afirmado. Os casos foram escolhidos pelos lugares onde este tipo de
código erra em silêncio: o casamento entre despacho e arquivo quando a mesma
unidade repete a etapa, a sessão que morreu sem se despedir, e a transcrição que
termina no meio de uma linha.
"""
import json
import importlib.machinery
import importlib.util
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MATERIAL = pathlib.Path(__file__).resolve().parent / "material"
MEDIR_BIN = RAIZ / "bin" / "orq-medir"

_loader = importlib.machinery.SourceFileLoader("orq_medir", str(MEDIR_BIN))
_spec = importlib.util.spec_from_loader("orq_medir", _loader)
medir = importlib.util.module_from_spec(_spec)
sys.modules["orq_medir"] = medir
_spec.loader.exec_module(medir)

# bin/orq (OA-01): usado para montar bancos de esteira no formato do modelo
# novo, do mesmo jeito que testes/test_vigia.py e testes/test_maquina.py.
_loader2 = importlib.machinery.SourceFileLoader("orq", str(RAIZ / "bin" / "orq"))
_spec2 = importlib.util.spec_from_loader("orq", _loader2)
orq = importlib.util.module_from_spec(_spec2)
sys.modules["orq"] = orq
_spec2.loader.exec_module(orq)


class Esquema(unittest.TestCase):
    def test_cria_e_repete_sem_erro(self):
        with tempfile.TemporaryDirectory() as d:
            alvo = pathlib.Path(d) / "m.db"
            medir.abrir(alvo).close()
            medir.abrir(alvo).close()          # segunda vez não pode explodir
            con = sqlite3.connect(alvo)
            nomes = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            con.close()
        for t in ("maquina", "esteira", "unidade", "sessao", "consumo",
                  "evento", "commit_unidade", "preco_modelo"):
            self.assertIn(t, nomes)

    def test_preco_nasce_vazio(self):
        # Preço é regra de negócio. Nenhum valor entra sozinho.
        with tempfile.TemporaryDirectory() as d:
            con = medir.abrir(pathlib.Path(d) / "m.db")
            n = con.execute("SELECT count(*) FROM preco_modelo").fetchone()[0]
            con.close()
        self.assertEqual(n, 0)


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

    def test_recusa_chave_toda_vazia(self):
        with self.assertRaises(ValueError):
            medir.chave_sessao("", "", "", "", "")


class Desfecho(unittest.TestCase):
    def test_traducao(self):
        self.assertEqual(medir.normalizar_desfecho("advanced:review"), "avancou")
        self.assertEqual(medir.normalizar_desfecho("hold"), "travou")
        self.assertEqual(medir.normalizar_desfecho("rejected->implement"), "reprovou")
        self.assertEqual(medir.normalizar_desfecho("reset"), "reiniciou")
        self.assertEqual(medir.normalizar_desfecho("loop-reset:1"), "orfa")

    def test_recolhimento_pela_rede_de_seguranca(self):
        # O motor arquiva sozinho o artefato de sessao que terminou sem se
        # despedir. Isso nao e falha, e nao pode ser contado como uma.
        self.assertEqual(medir.normalizar_desfecho("sweep:done"), "recolhida")
        self.assertEqual(medir.normalizar_desfecho("sweep:ready"), "recolhida")
        # Mas travada de verdade e orfa, como qualquer outra que morreu calada.
        self.assertEqual(medir.normalizar_desfecho("sweep:stalled"), "orfa")

    def test_volta_da_espera_humana_nao_e_falha(self):
        # O proprio motor registra: devolver para a fila e certo, contar falta
        # nao e. Somar isto a reiniciou inflaria a contagem de falhas.
        self.assertEqual(medir.normalizar_desfecho("release-requeue"), "retomada")
        self.assertNotEqual(medir.normalizar_desfecho("release-requeue"),
                            medir.normalizar_desfecho("reset"))

    def test_desconhecido_nao_vira_palpite(self):
        # Desfecho novo tem de aparecer como desconhecido, nunca ser encaixado
        # no balde mais parecido.
        self.assertIsNone(medir.normalizar_desfecho("coisa-nova"))
        self.assertIsNone(medir.normalizar_desfecho(None))


class SessoesArquivadas(unittest.TestCase):
    def test_le_as_tres_do_material(self):
        s = medir.sessoes_arquivadas(MATERIAL / "archive")
        self.assertEqual(len(s), 3)
        self.assertEqual({x["desfecho"] for x in s}, {"avancou", "travou", "orfa"})
        for x in s:
            self.assertTrue(x["fim"].endswith("Z"), x["fim"])
            self.assertTrue(x["unidade"])
            self.assertTrue(x["etapa"])
            self.assertTrue(x["tarefa"])
            self.assertTrue(x["esteira"])
            self.assertTrue(x["pasta"])

    def test_guarda_o_desfecho_original(self):
        s = medir.sessoes_arquivadas(MATERIAL / "archive")
        orfa = [x for x in s if x["desfecho"] == "orfa"][0]
        self.assertEqual(orfa["desfecho_bruto"], "loop-reset:1")


class Casamento(unittest.TestCase):
    """Onde este tipo de código erra: a mesma unidade repetindo a mesma etapa."""

    SESSOES = [
        {"esteira": "Q", "unidade": "FE-14", "etapa": "implement",
         "fim": "2026-08-31T22:10:00Z", "desfecho": "reprovou"},
        {"esteira": "Q", "unidade": "FE-14", "etapa": "implement",
         "fim": "2026-09-01T02:55:00Z", "desfecho": "avancou"},
    ]
    DESPACHOS = [
        {"pipeline": "Q", "unit": "FE-14", "stage": "implement",
         "ts": "2026-08-31T22:01:49Z", "id": "x", "branch": "CU-x-a"},
        {"pipeline": "Q", "unit": "FE-14", "stage": "implement",
         "ts": "2026-09-01T02:47:29Z", "id": "x", "branch": "CU-x-a"},
        {"pipeline": "Q", "unit": "FE-14", "stage": "implement",
         "ts": "2026-09-01T09:00:00Z", "id": "x", "branch": "CU-x-a"},
    ]

    def test_cada_sessao_pega_o_despacho_anterior_mais_proximo(self):
        r = medir.casar(self.SESSOES, self.DESPACHOS)
        fechadas = sorted([x for x in r if x.get("fim")], key=lambda x: x["fim"])
        self.assertEqual(fechadas[0]["inicio"], "2026-08-31T22:01:49Z")
        self.assertEqual(fechadas[1]["inicio"], "2026-09-01T02:47:29Z")
        self.assertFalse(fechadas[0]["inicio_deduzido"])

    def test_despacho_sem_sessao_vira_sessao_sem_fim(self):
        r = medir.casar(self.SESSOES, self.DESPACHOS)
        soltas = [x for x in r if not x.get("fim")]
        self.assertEqual(len(soltas), 1)
        self.assertEqual(soltas[0]["inicio"], "2026-09-01T09:00:00Z")
        self.assertIsNone(soltas[0]["desfecho"])

    def test_sessao_sem_despacho_tem_inicio_deduzido_e_marcado(self):
        r = medir.casar(self.SESSOES[:1], [])
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["inicio_deduzido"])
        self.assertEqual(r[0]["inicio"], r[0]["fim"])

    def test_nao_rouba_despacho_de_outra_etapa(self):
        outra = dict(self.DESPACHOS[0], stage="review")
        r = medir.casar(self.SESSOES[:1], [outra])
        fechada = [x for x in r if x.get("fim")][0]
        self.assertTrue(fechada["inicio_deduzido"])


class TarefaDoBranch(unittest.TestCase):
    def test_extrai_o_id(self):
        self.assertEqual(
            medir.tarefa_do_branch("CU-868abc002-ligar-o-otimizador-automatic"),
            "868abc002")

    def test_branch_de_fora_da_esteira(self):
        self.assertIsNone(medir.tarefa_do_branch("homol"))
        self.assertIsNone(medir.tarefa_do_branch(None))


class Consumo(unittest.TestCase):
    def test_soma_por_modelo(self):
        linhas = medir.consumo_de_transcricao(MATERIAL / "transcricao-curta.jsonl")
        self.assertEqual(len(linhas), 1)
        c = linhas[0]
        self.assertEqual(c["modelo"], "claude-opus-5")
        self.assertEqual(c["mensagens"], 2)
        self.assertEqual(c["tokens_saida"], 30)
        self.assertEqual(c["tokens_cache_leitura"], 300)
        self.assertEqual(c["tokens_entrada"], 8)
        self.assertEqual(c["tarefa"], "868abc002")
        self.assertEqual(c["primeiro_ts"], "2026-08-31T20:10:00Z")
        self.assertEqual(c["ultimo_ts"], "2026-08-31T20:11:00Z")

    def test_linha_truncada_nao_derruba_a_leitura(self):
        # Transcricao de sessao que morreu no meio termina numa linha partida.
        # Se isso derrubar a leitura, perde-se a sessao inteira em silencio.
        linhas = medir.consumo_de_transcricao(MATERIAL / "transcricao-curta.jsonl")
        self.assertTrue(linhas)


class JanelaDaSessao(unittest.TestCase):
    SESSOES = [
        {"id": 1, "inicio": "2026-08-31T20:00:00Z", "fim": "2026-08-31T20:30:00Z"},
        {"id": 2, "inicio": "2026-08-31T21:00:00Z", "fim": "2026-08-31T21:30:00Z"},
    ]

    def test_escolhe_a_janela_que_contem(self):
        self.assertEqual(medir.sessao_da_janela(self.SESSOES, "2026-08-31T20:10:00Z")["id"], 1)
        self.assertEqual(medir.sessao_da_janela(self.SESSOES, "2026-08-31T21:05:00Z")["id"], 2)

    def test_fora_de_qualquer_janela_nao_inventa(self):
        self.assertIsNone(medir.sessao_da_janela(self.SESSOES, "2026-08-31T20:45:00Z"))
        self.assertIsNone(medir.sessao_da_janela(self.SESSOES, None))

    def test_sessao_sem_fim_nao_engole_tudo(self):
        abertas = [{"id": 3, "inicio": "2026-08-31T20:00:00Z", "fim": None}]
        self.assertIsNone(medir.sessao_da_janela(abertas, "2026-09-05T00:00:00Z"))


class EventosDoLaco(unittest.TestCase):
    ESTADO = {
        "ticks": 366, "dispatched": 85,
        "quarantine": ["868abc004"],
        "rework": {"868abc001": 1, "868abc004": 2},
        "hold": {"868abc003": {"reason": "falta decidir a altura do botão",
                               "at": "2026-09-01T03:44:10Z",
                               "status": "em progresso"}},
    }

    def test_retrabalho_vira_evento_por_tarefa(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        r = [e for e in ev if e["tipo"] == "retrabalho"]
        self.assertEqual({e["tarefa"] for e in r}, {"868abc001", "868abc004"})

    def test_espera_humana_carrega_hora_e_motivo(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        h = [e for e in ev if e["tipo"] == "espera_humana"][0]
        self.assertEqual(h["ts"], "2026-09-01T03:44:10Z")
        self.assertIn("altura do botão", h["texto"])
        self.assertEqual(h["tarefa"], "868abc003")

    def test_quarentena(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        q = [e for e in ev if e["tipo"] == "quarentena"]
        self.assertEqual(len(q), 1)

    def test_toda_chave_e_unica(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        self.assertEqual(len({e["chave"] for e in ev}), len(ev))


class EventosDeGancho(unittest.TestCase):
    LINHAS = ("2026-09-01T02:32:08Z\tstop\tConfira o board: orq status\n"
              "2026-09-01T02:33:08Z\tnotification\tClaude is waiting for your input\n"
              "\n")

    def test_le_hora_tipo_e_texto(self):
        ev = medir.eventos_de_gancho(self.LINHAS, "FE-01", "servidor")
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0]["tipo"], "stop")
        self.assertEqual(ev[1]["ts"], "2026-09-01T02:33:08Z")
        self.assertIn("waiting", ev[1]["texto"])


class Comentarios(unittest.TestCase):
    PAYLOAD = {"comments": [
        {"id": "1", "date": "1788211481689",
         "user": {"username": "Fulano de Tal", "id": 1},
         "comment_text": "INTEGRADO E PUBLICADO. merge-base ae43e34, commit c461c71."},
        {"id": "2", "date": "1788200000000",
         "user": {"username": "Fulano de Tal", "id": 1},
         "comment_text": "REPROVADO (retrabalho 1/2) - volta para spec pronta."},
        {"id": "3", "date": "1788190000000",
         "user": {"username": "Fulano de Tal", "id": 1},
         "comment_text": "Spec publicada: ponto de partida medido."},
    ]}

    def test_hora_em_utc_e_autor(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868abc001", "servidor")
        self.assertTrue(all(e["ts"].endswith("Z") for e in ev))
        self.assertTrue(all(e["autor"] == "Fulano de Tal" for e in ev))
        self.assertEqual(len(ev), 3)

    def test_classifica_a_transicao(self):
        tipos = {e["tipo"] for e in
                 medir.eventos_de_comentarios(self.PAYLOAD, "868abc001", "servidor")}
        self.assertIn("integrado", tipos)
        self.assertIn("reprovado", tipos)
        self.assertIn("spec_publicada", tipos)

    def test_comentario_comum_nao_vira_transicao(self):
        p = {"comments": [{"id": "9", "date": "1788190000000",
                           "user": {"username": "Alguem"},
                           "comment_text": "bom dia, alguma novidade?"}]}
        ev = medir.eventos_de_comentarios(p, "868abc001", "servidor")
        self.assertEqual(ev[0]["tipo"], "comentario")

    def test_extrai_commits_citados(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868abc001", "servidor")
        shas = {s for e in ev for s in e["commits"]}
        self.assertIn("c461c71", shas)
        self.assertIn("ae43e34", shas)

    def test_nao_confunde_palavra_com_commit(self):
        # "decidida" e "cadastro" sao hexadecimais? nao. Mas "acessada" tem 8
        # letras e nenhuma fora de a-f seria um falso positivo classico.
        p = {"comments": [{"id": "9", "date": "1788190000000",
                           "user": {"username": "A"},
                           "comment_text": "a decisao foi acessada e efetivada."}]}
        ev = medir.eventos_de_comentarios(p, "868abc001", "servidor")
        self.assertEqual(ev[0]["commits"], [])


class UnidadesDeclaradas(unittest.TestCase):
    TOML = """
[pipeline]
name        = "Qualidade do Front-end"
repo        = "/home/orq/repos/app-exemplo"
base_branch = "homol"

[[task]]
id = "868abc001"
key = "FE-01"
title = "Erro numa tela nao pode apagar o aplicativo inteiro"
depends_on = []
mode = "autonomous"

[[task]]
id = "868abc007"
key = "FE-09"
title = "Remover as bibliotecas que o produto carrega e nao usa"
depends_on = ["FE-01"]
mode = "hands-on"
"""

    def test_le_codigo_tarefa_e_titulo(self):
        d = medir.tomllib.loads(self.TOML)
        u = medir.unidades_do_toml(d)
        self.assertEqual(len(u), 2)
        self.assertEqual(u[0]["codigo"], "FE-01")
        self.assertEqual(u[0]["tarefa"], "868abc001")
        self.assertIn("Erro numa tela", u[0]["titulo"])

    def test_le_a_configuracao_da_esteira(self):
        d = medir.tomllib.loads(self.TOML)
        c = medir.config_da_esteira(d)
        self.assertEqual(c["nome"], "Qualidade do Front-end")
        self.assertEqual(c["base"], "homol")
        self.assertTrue(c["repo"].endswith("app-exemplo"))

    def test_esteira_sem_tarefas_nao_explode(self):
        u = medir.unidades_do_toml(medir.tomllib.loads('[pipeline]\nname = "X"\n'))
        self.assertEqual(u, [])


class BranchDoMerge(unittest.TestCase):
    """A atribuicao de commit a unidade sai do merge, nao do intervalo.

    O intervalo base..branch mente quando a base local esta atrasada: ele
    devolve o trabalho de todas as unidades, e a chave primaria do commit faz a
    atribuicao ficar com quem rodou por ultimo. Ja aconteceu: uma unidade
    apareceu com 147 commits e 91 mil linhas que nao eram dela.
    """

    def test_merge_de_pedido_de_alteracao(self):
        self.assertEqual(
            medir.branch_do_merge(
                "Merge pull request #35 from org-exemplo/CU-868abc005-escolher-entre-tabela-e-cart"),
            "CU-868abc005-escolher-entre-tabela-e-cart")

    def test_merge_de_branch_simples(self):
        self.assertEqual(
            medir.branch_do_merge("Merge branch 'CU-868abc001-erro-numa-tela' into homol"),
            "CU-868abc001-erro-numa-tela")

    def test_merge_que_nao_e_de_unidade(self):
        self.assertIsNone(medir.branch_do_merge("Merge branch 'main' into homol"))
        self.assertIsNone(medir.branch_do_merge("feat: qualquer coisa"))
        self.assertIsNone(medir.branch_do_merge(None))


class Exportacao(unittest.TestCase):
    def test_traz_tabelas_e_vistas_e_serializa(self):
        with tempfile.TemporaryDirectory() as d:
            con = medir.abrir(pathlib.Path(d) / "m.db")
            dados = medir.exportar(con)
            con.close()
        for chave in ("maquina", "esteira", "unidade", "sessao", "consumo",
                      "evento", "commit_unidade", "preco_modelo",
                      "v_sessao", "v_retrabalho", "v_tempo_por_etapa"):
            self.assertIn(chave, dados["tabelas"])
        self.assertIn("gerado_em", dados)
        self.assertIn("limites", dados)
        json.dumps(dados)     # tem de serializar sozinho, sem conversor

    def test_declara_os_limites_do_proprio_dado(self):
        # Um numero sem a ressalva vira decisao errada. Os limites viajam junto.
        with tempfile.TemporaryDirectory() as d:
            con = medir.abrir(pathlib.Path(d) / "m.db")
            lim = medir.exportar(con)["limites"]
            con.close()
        texto = " ".join(lim).lower()
        self.assertIn("memoria", texto)
        self.assertIn("deduzid", texto)


class SessaoViva(unittest.TestCase):
    PREFIXO = "orq-qualidade-do-fro-"

    def test_tira_a_tarefa_do_nome_da_sessao(self):
        self.assertEqual(
            medir.tarefa_da_sessao(self.PREFIXO + "868abc001", self.PREFIXO), "868abc001")

    def test_ignora_sessao_de_fora_da_esteira(self):
        self.assertIsNone(medir.tarefa_da_sessao("sessao-claude", self.PREFIXO))
        self.assertIsNone(medir.tarefa_da_sessao("orq-loop-qualidade-do-front", self.PREFIXO))

    def test_etapa_vem_do_arquivo_de_ordem_de_servico(self):
        arquivos = ["qualidade-do-fro-868abc001-integrate.brief.md",
                    "qualidade-do-fro-868abc006-review.brief.md",
                    "runs.jsonl"]
        self.assertEqual(medir.etapa_do_brief(arquivos, "868abc001"), "integrate")
        self.assertEqual(medir.etapa_do_brief(arquivos, "868abc006"), "review")

    def test_sem_ordem_de_servico_nao_inventa_etapa(self):
        self.assertIsNone(medir.etapa_do_brief(["runs.jsonl"], "868abc001"))


class MemoriaDaSessao(unittest.TestCase):
    def test_soma_o_grupo_de_processos(self):
        # ps -o rss= devolve uma linha por processo do grupo, em kB
        self.assertEqual(medir.soma_rss_kb(" 128400\n  95220\n   4100\n"), 227720)

    def test_saida_vazia_ou_suja_vira_zero(self):
        self.assertEqual(medir.soma_rss_kb(""), 0)
        self.assertEqual(medir.soma_rss_kb("RSS\nnada\n"), 0)

    def test_amostra_tem_chave_estavel_por_minuto(self):
        # Duas coletas no mesmo minuto nao podem virar duas amostras.
        a = medir.chave_amostra("2026-09-03T12:34:56Z", "868abc001")
        b = medir.chave_amostra("2026-09-03T12:34:12Z", "868abc001")
        self.assertEqual(a, b)
        c = medir.chave_amostra("2026-09-03T12:35:01Z", "868abc001")
        self.assertNotEqual(a, c)


# ============================================================================
# OA-13 — a medição adaptada ao banco da esteira (OA-01)
# ============================================================================

class SessoesDaEsteiraModeloNovo(unittest.TestCase):
    """`sessoes_da_esteira`: a sessão do modelo novo, já traduzida."""

    UNIDADES = [{"id": 1, "chave": "FE-01", "clickup_id": "868abc001",
                 "status": "revisao"}]
    SESSOES = [{"id": 10, "unidade_id": 1, "worktree": "/wt/fe-01",
                "branch": "CU-868abc001-x",
                "iniciada_em": "2026-09-10T10:00:00Z",
                "encerrada_em": "2026-09-10T10:36:00Z", "desfecho": "advance"}]

    def test_traduz_com_etapa_sentinela_e_inicio_medido(self):
        r = medir.sessoes_da_esteira(self.UNIDADES, self.SESSOES, "Q")
        self.assertEqual(len(r), 1)
        s = r[0]
        self.assertEqual(s["etapa"], medir.PAPEL_UNICO)
        self.assertEqual(s["unidade"], "FE-01")
        self.assertEqual(s["tarefa"], "868abc001")
        self.assertFalse(s["inicio_deduzido"])
        self.assertFalse(s["fim_deduzido"])
        self.assertEqual(s["inicio"], "2026-09-10T10:00:00Z")
        self.assertEqual(s["fim"], "2026-09-10T10:36:00Z")

    def test_sessao_em_curso_fica_sem_fim_mas_nao_e_descartada(self):
        aberta = [{"id": 11, "unidade_id": 1, "worktree": "/wt/fe-01",
                   "branch": "CU-868abc001-x", "iniciada_em": "2026-09-10T10:00:00Z",
                   "encerrada_em": None, "desfecho": None}]
        r = medir.sessoes_da_esteira(self.UNIDADES, aberta, "Q")
        self.assertEqual(len(r), 1)
        self.assertIsNone(r[0]["fim"])

    def test_sessao_de_unidade_desconhecida_e_descartada(self):
        orfa = [{"id": 12, "unidade_id": 999, "worktree": "/wt", "branch": "b",
                 "iniciada_em": "2026-09-10T10:00:00Z", "encerrada_em": None,
                 "desfecho": None}]
        self.assertEqual(medir.sessoes_da_esteira(self.UNIDADES, orfa, "Q"), [])


class EventosDaEsteiraModeloNovo(unittest.TestCase):
    """`eventos_da_esteira`: o tipo viaja sem tradução, a chave não colide
    entre bancos de esteiras diferentes com o mesmo id interno."""

    UNIDADES = [{"id": 1, "chave": "FE-01", "clickup_id": "868abc001"}]
    EVENTOS = [
        {"id": 1, "unidade_id": 1, "tipo": "despachada", "ts": "2026-09-10T10:00:00Z",
         "texto": ""},
        {"id": 2, "unidade_id": 1, "tipo": "pr_aberto", "ts": "2026-09-10T11:00:00Z",
         "texto": "PR #7"},
    ]

    def test_tipo_passa_sem_traducao(self):
        r = medir.eventos_da_esteira(self.UNIDADES, self.EVENTOS, "Q", "servidor")
        self.assertEqual({e["tipo"] for e in r}, {"despachada", "pr_aberto"})
        self.assertEqual([e["unidade"] for e in r], ["FE-01", "FE-01"])

    def test_chave_nao_colide_entre_esteiras_com_mesmo_id_de_evento(self):
        a = medir.eventos_da_esteira(self.UNIDADES, self.EVENTOS, "Q", "servidor")
        b = medir.eventos_da_esteira(self.UNIDADES, self.EVENTOS, "Outra", "servidor")
        self.assertEqual(len({e["chave"] for e in a + b}), 4)

    def test_evento_de_unidade_removida_nao_derruba(self):
        solto = [{"id": 3, "unidade_id": 999, "tipo": "declaracao",
                  "ts": "2026-09-10T10:00:00Z", "texto": ""}]
        r = medir.eventos_da_esteira(self.UNIDADES, solto, "Q", "servidor")
        self.assertIsNone(r[0]["unidade"])


class TempoRevisaoEDevolucao(unittest.TestCase):
    """Critérios de aceite da OA-13: tempo em revisão e taxa de devolução.

    Três PRs, dois devolvidos: FE-01 e FE-02 levam um 'retrabalho' antes de
    fundir, FE-03 funde limpo. `pr_aberto`/`pr_fundido` têm hora conhecida
    para o tempo em revisão sair batendo com o cálculo à mão.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = medir.abrir(pathlib.Path(self.tmp.name) / "m.db")
        eid = medir._id_esteira(self.con, "Q")
        for codigo in ("FE-01", "FE-02", "FE-03"):
            medir._id_unidade(self.con, eid, codigo, codigo)
        self.con.commit()

        eventos = [
            # FE-01: aberto às 10h, uma devolução, funde às 14h — 4h de revisão.
            {"unidade": "FE-01", "tipo": "pr_aberto", "ts": "2026-09-10T10:00:00Z",
             "origem": "evento", "autor": None, "texto": None,
             "chave": "k1"},
            {"unidade": "FE-01", "tipo": "retrabalho", "ts": "2026-09-10T11:00:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k2"},
            {"unidade": "FE-01", "tipo": "pr_fundido", "ts": "2026-09-10T14:00:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k3"},
            # FE-02: aberto às 09h, uma devolução, funde às 10h30 — 1h30.
            {"unidade": "FE-02", "tipo": "pr_aberto", "ts": "2026-09-10T09:00:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k4"},
            {"unidade": "FE-02", "tipo": "retrabalho", "ts": "2026-09-10T09:45:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k5"},
            {"unidade": "FE-02", "tipo": "pr_fundido", "ts": "2026-09-10T10:30:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k6"},
            # FE-03: funde limpo, sem devolução — 30min de revisão.
            {"unidade": "FE-03", "tipo": "pr_aberto", "ts": "2026-09-10T08:00:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k7"},
            {"unidade": "FE-03", "tipo": "pr_fundido", "ts": "2026-09-10T08:30:00Z",
             "origem": "evento", "autor": None, "texto": None, "chave": "k8"},
        ]
        medir.gravar_eventos(self.con, "servidor", eventos)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_tempo_em_revisao_bate_com_o_calculo_a_mao(self):
        por_codigo = {r["codigo"]: r["horas"]
                      for r in self.con.execute("SELECT * FROM v_tempo_revisao")}
        self.assertEqual(por_codigo["FE-01"], 4.0)
        self.assertEqual(por_codigo["FE-02"], 1.5)
        self.assertEqual(por_codigo["FE-03"], 0.5)

    def test_taxa_de_devolucao_duas_em_tres(self):
        r = self.con.execute(
            "SELECT count(*) AS total,"
            " sum(CASE WHEN devolucoes > 0 THEN 1 ELSE 0 END) AS com_devolucao"
            " FROM v_devolucao").fetchone()
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["com_devolucao"], 2)
        taxa = 100 * r["com_devolucao"] / r["total"]
        self.assertAlmostEqual(taxa, 66.67, places=1)

    def test_unidade_sem_pr_aberto_nao_entra_na_devolucao(self):
        eid = medir._id_esteira(self.con, "Q")
        medir._id_unidade(self.con, eid, "FE-04", "FE-04")
        self.con.commit()
        codigos = {r["codigo"] for r in self.con.execute("SELECT * FROM v_devolucao")}
        self.assertNotIn("FE-04", codigos)

    def test_espera_humana_ve_bloqueada_do_modelo_novo(self):
        medir.gravar_eventos(self.con, "servidor", [
            {"unidade": "FE-03", "tipo": "bloqueada", "ts": "2026-09-10T09:00:00Z",
             "origem": "evento", "autor": None,
             "texto": "3ª devolução — provavelmente é o requisito", "chave": "k9"},
        ])
        codigos = {r["codigo"] for r in self.con.execute("SELECT * FROM v_espera_humana")}
        self.assertIn("FE-03", codigos)


class SessaoDoPapelUnicoNaoMistuaComEtapaAntiga(unittest.TestCase):
    """A mediana por estágio some; a distribuição da sessão inteira fica no
    balde PAPEL_UNICO, separada do rastro de quatro estágios."""

    def test_sessao_nova_nao_entra_no_balde_de_etapa_antiga(self):
        with tempfile.TemporaryDirectory() as d:
            con = medir.abrir(pathlib.Path(d) / "m.db")
            eid = medir._id_esteira(con, "Q")
            medir._id_unidade(con, eid, "FE-01", "FE-01")
            n = medir.gravar_sessoes(con, "servidor", "corrente", [
                {"esteira": "Q", "unidade": "FE-01", "tarefa": None,
                 "etapa": medir.PAPEL_UNICO, "branch": None,
                 "inicio": "2026-09-10T10:00:00Z", "inicio_deduzido": False,
                 "fim": "2026-09-10T10:36:00Z", "fim_deduzido": False,
                 "desfecho": "advance", "desfecho_bruto": "advance",
                 "status_final": None, "pasta": "/wt"},
            ])
            self.assertEqual(n, 1)
            etapas = {r["etapa"] for r in con.execute("SELECT etapa FROM sessao")}
            con.close()
        self.assertEqual(etapas, {medir.PAPEL_UNICO})
        self.assertNotIn("spec", etapas)
        self.assertNotIn("implement", etapas)


class AtribuicaoPorPr(unittest.TestCase):
    """Critério de aceite da OA-13: atribuição pelo merge, agora pelo NÚMERO
    do PR — cobre squash (o padrão do GitHub), que `branch_do_merge` não
    alcança porque squash não cria commit de merge nenhum.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self._git("init", "-q", "-b", "homol")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "Teste")
        (self.repo / "a.txt").write_text("base\n")
        self._git("add", "a.txt")
        self._git("commit", "-q", "-m", "inicial")

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args):
        r = subprocess.run(["git", "-C", str(self.repo), *args],
                           capture_output=True, text=True, check=True)
        return r.stdout

    def test_squash_e_achado_pelo_numero_do_pr_nao_pelo_branch(self):
        self._git("checkout", "-q", "-b", "CU-868abc009-feature")
        (self.repo / "b.txt").write_text("linha 1\nlinha 2\n")
        self._git("add", "b.txt")
        self._git("commit", "-q", "-m", "trabalho da unidade")
        self._git("checkout", "-q", "homol")
        self._git("merge", "-q", "--squash", "CU-868abc009-feature")
        self._git("commit", "-q", "-m", "Ajusta o formulário (#42)")
        self._git("branch", "-q", "-D", "CU-868abc009-feature")   # branch some

        sha = medir.commit_do_pr(self.repo, "homol", 42)
        self.assertIsNotNone(sha)
        self.assertEqual(sha, self._git("rev-parse", "HEAD").strip())

        commits = medir.commits_do_merge(self.repo, sha)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["insercoes"], 2)
        self.assertEqual(commits[0]["arquivos"], 1)

    def test_merge_tradicional_tambem_e_achado_pelo_numero(self):
        self._git("checkout", "-q", "-b", "CU-868abc010-feature")
        (self.repo / "c.txt").write_text("x\n")
        self._git("add", "c.txt")
        self._git("commit", "-q", "-m", "trabalho")
        self._git("checkout", "-q", "homol")
        self._git("merge", "-q", "--no-ff", "-m",
                  "Merge pull request #7 from org/CU-868abc010-feature",
                  "CU-868abc010-feature")

        sha = medir.commit_do_pr(self.repo, "homol", 7)
        commits = medir.commits_do_merge(self.repo, sha)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["mensagem"], "trabalho")

    def test_numero_que_nao_existe_nao_inventa_sha(self):
        self.assertIsNone(medir.commit_do_pr(self.repo, "homol", 999))

    def test_coletar_producao_pr_grava_na_unidade_certa(self):
        self._git("checkout", "-q", "-b", "CU-868abc011-feature")
        (self.repo / "d.txt").write_text("um\ndois\ntres\n")
        self._git("add", "d.txt")
        self._git("commit", "-q", "-m", "trabalho")
        self._git("checkout", "-q", "homol")
        self._git("merge", "-q", "--squash", "CU-868abc011-feature")
        self._git("commit", "-q", "-m", "Feature nova (#101)")

        with tempfile.TemporaryDirectory() as d:
            con = medir.abrir(pathlib.Path(d) / "m.db")
            eid = medir._id_esteira(con, "Q")
            medir._id_unidade(con, eid, "FE-11", "FE-11")
            k = medir.coletar_producao_pr(
                con, self.repo, "homol", [{"chave": "FE-11", "pr_numero": 101}])
            self.assertEqual(k, 1)
            linhas = list(con.execute(
                "SELECT k.insercoes FROM commit_unidade k JOIN unidade u"
                " ON u.id = k.unidade_id WHERE u.codigo = 'FE-11'"))
            con.close()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["insercoes"], 3)


class ColetaSemRastroAntigo(unittest.TestCase):
    """Critério de aceite da OA-13: `orq-medir coletar` numa máquina que
    nunca teve o modelo velho sai 0 — com e sem banco de esteira presente.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.armazem = pathlib.Path(self.tmp.name) / "medicao.db"

    def tearDown(self):
        self.tmp.cleanup()

    def _coletar(self):
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(
            [sys.executable, str(MEDIR_BIN), "--armazem", str(self.armazem),
             "coletar", "--sem-rede"],
            capture_output=True, text=True, timeout=30, env=env)

    def test_nada_em_lugar_nenhum_sai_zero(self):
        r = self._coletar()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_so_banco_de_esteira_do_modelo_novo_sai_zero_e_coleta(self):
        bancos = self.home / ".config/orquestrador/esteiras"
        bancos.mkdir(parents=True)
        caminho = bancos / "qualidade.db"
        con = orq.criar_banco(caminho)
        con.execute("INSERT INTO config (chave, valor) VALUES ('name', 'Qualidade')")
        uid = orq.criar_unidade(con, "FE-01", clickup_id="868abc001", titulo="teste")
        con.commit()
        with orq.transacao(caminho) as con2:
            orq.registrar_sessao(con2, uid, worktree="/wt", branch="CU-868abc001-x")
            orq.encerrar_sessao(con2, uid, "advance")
        con.close()

        r = self._coletar()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Qualidade", r.stdout)

        con = medir.abrir(self.armazem)
        etapas = {r2["etapa"] for r2 in con.execute("SELECT etapa FROM sessao")}
        con.close()
        self.assertEqual(etapas, {medir.PAPEL_UNICO})


class ArquivoLegadoContinuaLegivel(unittest.TestCase):
    """Critério de aceite da OA-13: coletar sobre `testes/material/archive/`
    (modelo antigo) não explode, mesmo sem nenhum banco de esteira novo."""

    def test_coletar_sobre_material_legado_nao_explode(self):
        with tempfile.TemporaryDirectory() as d:
            home = pathlib.Path(d) / "home"
            estado = home / ".claude/orchestrator/state"
            estado.mkdir(parents=True)
            for pasta in (MATERIAL / "archive").iterdir():
                if pasta.is_dir():
                    import shutil
                    shutil.copytree(pasta, estado / "archive" / pasta.name)
            env = {**os.environ, "HOME": str(home)}
            r = subprocess.run(
                [sys.executable, str(MEDIR_BIN), "--armazem", str(pathlib.Path(d) / "m.db"),
                 "coletar", "--sem-rede"],
                capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("arquivadas", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
