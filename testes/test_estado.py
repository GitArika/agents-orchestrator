"""Testes do núcleo de estado em SQLite (OA-01).

Cobre os seis critérios de aceite de
docs/specs/orquestrador-agil/OA-01-nucleo-sqlite.md: pragmas, escrita
concorrente sem perda, resiliência a queda no meio, estado que nunca volta
vazio em silêncio, recusa de dependência cíclica e rastro completo por
transição.

Carrega bin/orq pelo mesmo padrão de testes/test_orq.py: função pura, sem
precisar do CLI nem do pipeline.toml.
"""
import importlib.machinery
import importlib.util
import multiprocessing
import os
import signal
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("orq", str(RAIZ / "bin" / "orq"))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


def _escrever_transicao(caminho, unidade_id, status, n):
    """Roda num PROCESSO separado: escreve uma transição e um evento, uma vez.
    Módulo-level de propósito — multiprocessing precisa poder fazer pickle."""
    import importlib.machinery, importlib.util, sys as _sys
    loader = importlib.machinery.SourceFileLoader("orq", str(RAIZ / "bin" / "orq"))
    spec = importlib.util.spec_from_loader("orq", loader)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["orq"] = mod
    spec.loader.exec_module(mod)
    with mod.transacao(caminho) as con:
        mod.definir_status(con, unidade_id, status, motivo=f"escritor {n}")


class BancoNovo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_nasce_com_wal_fk_e_timeout(self):
        con = orq.criar_banco(self.caminho)
        try:
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(con.execute("PRAGMA busy_timeout").fetchone()[0], 10000)
        finally:
            con.close()

    def test_permissao_do_arquivo_e_pessoal(self):
        con = orq.criar_banco(self.caminho)
        con.close()
        modo = oct(self.caminho.stat().st_mode)[-3:]
        self.assertEqual(modo, "600")

    def test_recusa_sobrescrever_sem_forcar(self):
        orq.criar_banco(self.caminho).close()
        with self.assertRaises(SystemExit):
            orq.criar_banco(self.caminho)

    def test_forcar_recria_do_zero(self):
        con = orq.criar_banco(self.caminho)
        orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="t")
        con.close()
        con2 = orq.criar_banco(self.caminho, forcar=True)
        n = con2.execute("SELECT count(*) FROM unidade").fetchone()[0]
        con2.close()
        self.assertEqual(n, 0)

    def test_esquema_tem_as_tabelas_principais(self):
        con = orq.criar_banco(self.caminho)
        nomes = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        for esperado in ("unidade", "dependencia", "evento", "sessao", "config"):
            self.assertIn(esperado, nomes)

    def test_esquema_nao_tem_tabela_de_portao(self):
        # Decisão de 22/09/2026: gates saem do orquestrador — quem executa é o
        # agente, seguindo o CLAUDE.md do projeto. Não há mais nada para
        # declarar aqui (ver docs/specs/orquestrador-agil/OA-02).
        con = orq.criar_banco(self.caminho)
        nomes = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        self.assertNotIn("portao", nomes)


class EstadoNuncaVoltaVazioEmSilencio(unittest.TestCase):
    """O defeito que este núcleo substitui: `loop_state` engolia exceção e
    devolvia `{}`. Aqui, toda falha de leitura é uma exceção que aparece."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_banco_inexistente_levanta_em_vez_de_devolver_vazio(self):
        with self.assertRaises(orq.ErroEstado):
            orq.abrir_banco(self.caminho)

    def test_banco_corrompido_levanta_em_vez_de_devolver_vazio(self):
        self.caminho.write_bytes(b"isto nao e um banco sqlite valido, so lixo")
        with self.assertRaises(orq.ErroEstado):
            orq.abrir_banco(self.caminho)

    def test_banco_sem_tabela_esquema_levanta(self):
        con = sqlite3.connect(self.caminho)
        con.execute("CREATE TABLE outra_coisa (x INTEGER)")
        con.commit()
        con.close()
        with self.assertRaises(orq.ErroEstado):
            orq.abrir_banco(self.caminho)

    def test_versao_maior_que_a_conhecida_recusa(self):
        con = orq.criar_banco(self.caminho)
        con.execute("UPDATE esquema SET versao = 999")
        con.commit()
        con.close()
        with self.assertRaises(orq.ErroEstado):
            orq.abrir_banco(self.caminho)


class TransacaoEEvento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="868x", titulo="Teste")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_toda_transicao_grava_evento_na_mesma_transacao(self):
        with orq.transacao(self.caminho) as con:
            orq.definir_status(con, self.uid, "em_progresso")
        con = orq.abrir_banco(self.caminho)
        eventos = con.execute(
            "SELECT tipo, de_status, para_status FROM evento "
            "WHERE unidade_id = ? AND tipo = 'transicao'", (self.uid,)).fetchall()
        con.close()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["de_status"], "backlog")
        self.assertEqual(eventos[0]["para_status"], "em_progresso")

    def test_falha_no_meio_desfaz_tudo(self):
        with self.assertRaises(RuntimeError):
            with orq.transacao(self.caminho) as con:
                orq.definir_status(con, self.uid, "em_progresso")
                raise RuntimeError("falha deliberada no meio da transação")
        con = orq.abrir_banco(self.caminho)
        status = con.execute(
            "SELECT status FROM unidade WHERE id = ?", (self.uid,)).fetchone()["status"]
        n_eventos = con.execute(
            "SELECT count(*) FROM evento WHERE tipo = 'transicao'").fetchone()[0]
        con.close()
        self.assertEqual(status, "backlog")   # nada mudou
        self.assertEqual(n_eventos, 0)        # nem o evento ficou meio-gravado

    def test_declaracao_da_unidade_ja_deixou_evento(self):
        con = orq.abrir_banco(self.caminho)
        n = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'declaracao'",
            (self.uid,)).fetchone()[0]
        con.close()
        self.assertEqual(n, 1)


class DependenciaCiclica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        self.b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        self.c = orq.criar_unidade(con, "FE-C", clickup_id="3", titulo="c")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_dependencia_direta_simples_passa(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)   # B depende de A
        con = orq.abrir_banco(self.caminho)
        n = con.execute("SELECT count(*) FROM dependencia").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    def test_autodependencia_recusa(self):
        with self.assertRaises(orq.ErroDependenciaCiclica):
            with orq.transacao(self.caminho) as con:
                orq.adicionar_dependencia(con, self.a, self.a)

    def test_ciclo_direto_recusa_com_caminho(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)   # B -> A
        with self.assertRaises(orq.ErroDependenciaCiclica) as ctx:
            with orq.transacao(self.caminho) as con:
                orq.adicionar_dependencia(con, self.a, self.b)   # A -> B fecharia o ciclo
        self.assertIn("FE-A", str(ctx.exception))
        self.assertIn("FE-B", str(ctx.exception))

    def test_ciclo_transitivo_recusa(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)   # B -> A
            orq.adicionar_dependencia(con, self.c, self.b)   # C -> B
        with self.assertRaises(orq.ErroDependenciaCiclica):
            with orq.transacao(self.caminho) as con:
                orq.adicionar_dependencia(con, self.a, self.c)   # A -> C fecharia A->C->B->A

    def test_ciclo_recusado_nao_deixa_nada_gravado(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)
        with self.assertRaises(orq.ErroDependenciaCiclica):
            with orq.transacao(self.caminho) as con:
                orq.adicionar_dependencia(con, self.a, self.b)
        con = orq.abrir_banco(self.caminho)
        n = con.execute("SELECT count(*) FROM dependencia").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)   # só a B->A original


@unittest.skipIf(sys.platform == "win32", "fork não existe no Windows")
class EscritaConcorrente(unittest.TestCase):
    """20 processos gravando transições na MESMA unidade. Nenhum pode perder a
    escrita do outro — é o critério de aceite central de OA-01."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="t")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_vinte_escritores_nenhuma_perda(self):
        N = 20
        ctx = multiprocessing.get_context("fork") if hasattr(os, "fork") \
            else multiprocessing.get_context("spawn")
        procs = [ctx.Process(target=_escrever_transicao,
                             args=(self.caminho, self.uid, "em_progresso", i))
                for i in range(N)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)
            self.assertEqual(p.exitcode, 0, "um escritor falhou ou travou")

        con = orq.abrir_banco(self.caminho)
        n_eventos = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'transicao'",
            (self.uid,)).fetchone()[0]
        status_final = con.execute(
            "SELECT status FROM unidade WHERE id = ?", (self.uid,)).fetchone()["status"]
        con.close()
        self.assertEqual(n_eventos, N, "escrita concorrente perdeu atualização")
        self.assertEqual(status_final, "em_progresso")


@unittest.skipUnless(hasattr(os, "fork"), "kill -9 mid-transação exige fork")
class QuedaNoMeioNaoCorrompe(unittest.TestCase):
    """Mata um escritor com SIGKILL enquanto ele segura o lock, ANTES do
    commit. O banco precisa continuar íntegro e com o estado anterior."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="t")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_kill_no_meio_da_transacao_preserva_o_estado_anterior(self):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(r)
            con = orq.abrir_banco(self.caminho)
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE unidade SET status = 'bloqueado' WHERE id = ?",
                       (self.uid,))
            os.write(w, b"x")   # avisa o pai que já escreveu, mas NÃO deu commit
            os.close(w)
            time.sleep(30)      # espera o pai matar
            os._exit(1)         # não deveria chegar aqui
        else:
            os.close(w)
            os.read(r, 1)       # espera a escrita não-commitada acontecer
            os.close(r)
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)

            con = orq.abrir_banco(self.caminho)
            status = con.execute(
                "SELECT status FROM unidade WHERE id = ?", (self.uid,)).fetchone()["status"]
            con.close()
            self.assertEqual(status, "backlog",
                            "a escrita não-commitada vazou apesar do kill -9")

            # E o banco continua utilizável: outra escrita completa normalmente.
            with orq.transacao(self.caminho) as con2:
                orq.definir_status(con2, self.uid, "em_progresso")
            con = orq.abrir_banco(self.caminho)
            status = con.execute(
                "SELECT status FROM unidade WHERE id = ?", (self.uid,)).fetchone()["status"]
            con.close()
            self.assertEqual(status, "em_progresso")


class CaminhoPadraoDoBanco(unittest.TestCase):
    def test_um_arquivo_por_esteira_no_diretorio_convencional(self):
        caminho = orq.caminho_banco_padrao("front-end")
        self.assertEqual(caminho.parent, orq.BANCOS)
        self.assertTrue(caminho.name.endswith(".db"))

    def test_nome_e_reduzido_a_slug(self):
        caminho = orq.caminho_banco_padrao("Front End / Épico 2")
        self.assertNotIn(" ", caminho.name)
        self.assertNotIn("/", caminho.name)


if __name__ == "__main__":
    unittest.main()
