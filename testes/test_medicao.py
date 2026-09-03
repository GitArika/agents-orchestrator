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
import pathlib
import sqlite3
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MATERIAL = pathlib.Path(__file__).resolve().parent / "material"

_loader = importlib.machinery.SourceFileLoader("orq_medir", str(RAIZ / "bin" / "orq-medir"))
_spec = importlib.util.spec_from_loader("orq_medir", _loader)
medir = importlib.util.module_from_spec(_spec)
sys.modules["orq_medir"] = medir
_spec.loader.exec_module(medir)


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
            medir.tarefa_do_branch("CU-868kyu9v4-ligar-o-otimizador-automatic"),
            "868kyu9v4")

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
        self.assertEqual(c["tarefa"], "868kyu9v4")
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
        "quarantine": ["868kyu8ec"],
        "rework": {"868kyu71z": 1, "868kyu8ec": 2},
        "hold": {"868kyugea": {"reason": "falta decidir a altura do botão",
                               "at": "2026-09-01T03:44:10Z",
                               "status": "em progresso"}},
    }

    def test_retrabalho_vira_evento_por_tarefa(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        r = [e for e in ev if e["tipo"] == "retrabalho"]
        self.assertEqual({e["tarefa"] for e in r}, {"868kyu71z", "868kyu8ec"})

    def test_espera_humana_carrega_hora_e_motivo(self):
        ev = medir.eventos_do_laco(self.ESTADO, "Q", "servidor")
        h = [e for e in ev if e["tipo"] == "espera_humana"][0]
        self.assertEqual(h["ts"], "2026-09-01T03:44:10Z")
        self.assertIn("altura do botão", h["texto"])
        self.assertEqual(h["tarefa"], "868kyugea")

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
         "user": {"username": "Ariel Evangelista", "id": 1},
         "comment_text": "INTEGRADO E PUBLICADO. merge-base ae43e34, commit c461c71."},
        {"id": "2", "date": "1788200000000",
         "user": {"username": "Ariel Evangelista", "id": 1},
         "comment_text": "REPROVADO (retrabalho 1/2) - volta para spec pronta."},
        {"id": "3", "date": "1788190000000",
         "user": {"username": "Ariel Evangelista", "id": 1},
         "comment_text": "Spec publicada: ponto de partida medido."},
    ]}

    def test_hora_em_utc_e_autor(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z", "servidor")
        self.assertTrue(all(e["ts"].endswith("Z") for e in ev))
        self.assertTrue(all(e["autor"] == "Ariel Evangelista" for e in ev))
        self.assertEqual(len(ev), 3)

    def test_classifica_a_transicao(self):
        tipos = {e["tipo"] for e in
                 medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z", "servidor")}
        self.assertIn("integrado", tipos)
        self.assertIn("reprovado", tipos)
        self.assertIn("spec_publicada", tipos)

    def test_comentario_comum_nao_vira_transicao(self):
        p = {"comments": [{"id": "9", "date": "1788190000000",
                           "user": {"username": "Alguem"},
                           "comment_text": "bom dia, alguma novidade?"}]}
        ev = medir.eventos_de_comentarios(p, "868kyu71z", "servidor")
        self.assertEqual(ev[0]["tipo"], "comentario")

    def test_extrai_commits_citados(self):
        ev = medir.eventos_de_comentarios(self.PAYLOAD, "868kyu71z", "servidor")
        shas = {s for e in ev for s in e["commits"]}
        self.assertIn("c461c71", shas)
        self.assertIn("ae43e34", shas)

    def test_nao_confunde_palavra_com_commit(self):
        # "decidida" e "cadastro" sao hexadecimais? nao. Mas "acessada" tem 8
        # letras e nenhuma fora de a-f seria um falso positivo classico.
        p = {"comments": [{"id": "9", "date": "1788190000000",
                           "user": {"username": "A"},
                           "comment_text": "a decisao foi acessada e efetivada."}]}
        ev = medir.eventos_de_comentarios(p, "868kyu71z", "servidor")
        self.assertEqual(ev[0]["commits"], [])


class UnidadesDeclaradas(unittest.TestCase):
    TOML = """
[pipeline]
name        = "Qualidade do Front-end"
repo        = "/home/orq/repos/app-exemplo"
base_branch = "homol"

[[task]]
id = "868kyu71z"
key = "FE-01"
title = "Erro numa tela nao pode apagar o aplicativo inteiro"
depends_on = []
mode = "autonomous"

[[task]]
id = "868kyu92r"
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
        self.assertEqual(u[0]["tarefa"], "868kyu71z")
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
                "Merge pull request #35 from exemplo-org/CU-868abc009-escolher-entre-tabela-e-cart"),
            "CU-868abc009-escolher-entre-tabela-e-cart")

    def test_merge_de_branch_simples(self):
        self.assertEqual(
            medir.branch_do_merge("Merge branch 'CU-868kyu71z-erro-numa-tela' into homol"),
            "CU-868kyu71z-erro-numa-tela")

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
            medir.tarefa_da_sessao(self.PREFIXO + "868kyu71z", self.PREFIXO), "868kyu71z")

    def test_ignora_sessao_de_fora_da_esteira(self):
        self.assertIsNone(medir.tarefa_da_sessao("sessao-claude", self.PREFIXO))
        self.assertIsNone(medir.tarefa_da_sessao("orq-loop-qualidade-do-front", self.PREFIXO))

    def test_etapa_vem_do_arquivo_de_ordem_de_servico(self):
        arquivos = ["qualidade-do-fro-868kyu71z-integrate.brief.md",
                    "qualidade-do-fro-868kyugkg-review.brief.md",
                    "runs.jsonl"]
        self.assertEqual(medir.etapa_do_brief(arquivos, "868kyu71z"), "integrate")
        self.assertEqual(medir.etapa_do_brief(arquivos, "868kyugkg"), "review")

    def test_sem_ordem_de_servico_nao_inventa_etapa(self):
        self.assertIsNone(medir.etapa_do_brief(["runs.jsonl"], "868kyu71z"))


class MemoriaDaSessao(unittest.TestCase):
    def test_soma_o_grupo_de_processos(self):
        # ps -o rss= devolve uma linha por processo do grupo, em kB
        self.assertEqual(medir.soma_rss_kb(" 128400\n  95220\n   4100\n"), 227720)

    def test_saida_vazia_ou_suja_vira_zero(self):
        self.assertEqual(medir.soma_rss_kb(""), 0)
        self.assertEqual(medir.soma_rss_kb("RSS\nnada\n"), 0)

    def test_amostra_tem_chave_estavel_por_minuto(self):
        # Duas coletas no mesmo minuto nao podem virar duas amostras.
        a = medir.chave_amostra("2026-09-03T12:34:56Z", "868kyu71z")
        b = medir.chave_amostra("2026-09-03T12:34:12Z", "868kyu71z")
        self.assertEqual(a, b)
        c = medir.chave_amostra("2026-09-03T12:35:01Z", "868kyu71z")
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
