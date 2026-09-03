"""Testes do medidor da esteira.

O medidor é função pura sobre arquivos, então tudo aqui é material congelado com
resultado afirmado. Os casos foram escolhidos pelos lugares onde este tipo de
código erra em silêncio: o casamento entre despacho e arquivo quando a mesma
unidade repete a etapa, a sessão que morreu sem se despedir, e a transcrição que
termina no meio de uma linha.
"""
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
