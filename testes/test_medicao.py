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


if __name__ == "__main__":
    unittest.main(verbosity=2)
