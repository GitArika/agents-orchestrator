"""Testes do espelho de cinco status no ClickUp — o lado Python (OA-07):
`_espelhar_pronto`, `_espelho_divergente`/`⚠` no `orq board`, e o contrato
escrito no BRIEFING único (OA-05).

O provisionamento da lista (`orq-clickup padronizar`) tem suíte própria:
testes/test_padronizar.py. Aqui é o que o MOTOR (bin/orq) faz: a única
escrita automática (`pronto`, quando o vigia detecta o merge — OA-08), o
sinal de divergência no quadro, e as instruções que o agente recebe para
escrever os outros dois lados.

Nenhum teste aqui fala com o ClickUp real — `orq-clickup` é o de mentira em
testes/fixtures/bin/orq-clickup, escolhido por ORQ_CLICKUP_CMD.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORQ_BIN = RAIZ / "bin" / "orq"
FAKE_BIN = RAIZ / "testes" / "fixtures" / "bin"

os.environ.setdefault("ORQ_NOTIFY_CMD", str(FAKE_BIN / "orq-avisar"))
os.environ.setdefault("ORQ_CLICKUP_CMD", str(FAKE_BIN / "orq-clickup"))

_loader = importlib.machinery.SourceFileLoader("orq", str(ORQ_BIN))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


class ComEnvSeguro(unittest.TestCase):
    """Salva/restaura ORQ_CLICKUP_CMD e as variáveis FAKE_CLICKUP_* entre
    testes — cada um decide seu próprio comportamento do orq-clickup de
    mentira sem vazar para o próximo."""

    def setUp(self):
        self._clickup_cmd_original = os.environ.get("ORQ_CLICKUP_CMD")
        os.environ["ORQ_CLICKUP_CMD"] = str(FAKE_BIN / "orq-clickup")
        for k in list(os.environ):
            if k.startswith("FAKE_CLICKUP_"):
                del os.environ[k]

    def tearDown(self):
        if self._clickup_cmd_original is None:
            os.environ.pop("ORQ_CLICKUP_CMD", None)
        else:
            os.environ["ORQ_CLICKUP_CMD"] = self._clickup_cmd_original
        for k in list(os.environ):
            if k.startswith("FAKE_CLICKUP_"):
                del os.environ[k]


class EspelharPronto(ComEnvSeguro):
    def test_sem_clickup_id_devolve_mensagem_sem_chamar_nada(self):
        erro = orq._espelhar_pronto(None)
        self.assertIsNotNone(erro)
        self.assertIn("clickup_id", erro)

    def test_sucesso_devolve_none(self):
        self.assertIsNone(orq._espelhar_pronto("123"))

    def test_falha_devolve_o_erro_sem_levantar(self):
        os.environ["FAKE_CLICKUP_FAIL"] = "1"
        erro = orq._espelhar_pronto("123")
        self.assertIsNotNone(erro)

    def test_binario_ausente_nunca_levanta(self):
        os.environ["ORQ_CLICKUP_CMD"] = "/caminho/que/nao/existe/orq-clickup-fantasma"
        erro = orq._espelhar_pronto("123")
        self.assertIsNotNone(erro)

    def test_chama_set_status_pronto_com_o_id_certo(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "chamadas.jsonl"
            os.environ["FAKE_CLICKUP_LOG"] = str(log)
            orq._espelhar_pronto("868001")
            linhas = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertEqual(linhas, [{"taskId": "868001", "status": "pronto"}])


class ConcluirMergeEscreveOEspelho(ComEnvSeguro):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="868001", titulo="a")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_sucesso_registra_espelho_ok(self):
        achado = {"unidade_id": self.a, "chave": "FE-A", "clickup_id": "868001",
                 "worktree": None, "branch": None}
        orq._concluir_merge(self.caminho, None, "esteira", achado)
        con = orq.abrir_banco(self.caminho)
        ev = con.execute(
            "SELECT texto FROM evento WHERE unidade_id = ? AND tipo = 'espelho_ok'",
            (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)

    def test_falha_registra_espelho_falhou_sem_impedir_o_pronto(self):
        os.environ["FAKE_CLICKUP_FAIL"] = "1"
        achado = {"unidade_id": self.a, "chave": "FE-A", "clickup_id": "868001",
                 "worktree": None, "branch": None}
        resultado = orq._concluir_merge(self.caminho, None, "esteira", achado)
        self.assertIn("pronto", resultado)   # a transição já aconteceu, isto só relata

        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()
        ev = con.execute(
            "SELECT texto FROM evento WHERE unidade_id = ? AND tipo = 'espelho_falhou'",
            (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)


class EspelhoDivergenteNoBoard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _marcar(self, *tipos):
        with orq.transacao(self.caminho) as con:
            for tipo in tipos:
                orq.registrar_evento(con, self.a, tipo)

    def test_sem_eventos_nao_diverge(self):
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq._espelho_divergente(con, self.a))
        con.close()

    def test_so_espelho_ok_nao_diverge(self):
        self._marcar("espelho_ok")
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq._espelho_divergente(con, self.a))
        con.close()

    def test_ultimo_espelho_falhou_diverge(self):
        self._marcar("espelho_ok", "espelho_falhou")
        con = orq.abrir_banco(self.caminho)
        self.assertTrue(orq._espelho_divergente(con, self.a))
        con.close()

    def test_recupera_quando_espelho_ok_e_mais_recente(self):
        self._marcar("espelho_falhou", "espelho_ok")
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq._espelho_divergente(con, self.a))
        con.close()

    def test_orq_board_mostra_o_aviso(self):
        self._marcar("espelho_falhou")
        con = orq.abrir_banco(self.caminho)
        linhas = orq.classificar(con)
        con.close()
        self.assertTrue(linhas[0]["espelho_divergente"])

    def test_orq_board_como_subprocesso_imprime_o_simbolo(self):
        self._marcar("espelho_falhou")
        r = subprocess.run([sys.executable, str(ORQ_BIN), "--db", str(self.caminho), "board"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("⚠", r.stdout)
        self.assertIn("FE-A", r.stdout)


class ContratoNoBriefing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        for chave, valor in {"name": "esteira", "base_branch": "main",
                             "repo": "/repo", "github_repo": "acme/app"}.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="868001", titulo="a")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _briefing(self):
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT * FROM unidade WHERE id = ?", (self.uid,)).fetchone()
        texto = orq.build_brief(con, u, Path("/tmp/wt"), "CU-868001-x")
        con.close()
        return texto

    def test_marca_em_progresso_antes_de_ler_a_tarefa_sem_comentario(self):
        texto = self._briefing()
        pos_status = texto.index('orq-clickup set-status 868001 "em progresso"')
        pos_show = texto.index("orq-clickup show 868001")
        self.assertLess(pos_status, pos_show)
        self.assertIn("SEM comentário", texto)

    def test_encerramento_com_pr_escreve_revisao_e_comenta_sem_flag_quebrada(self):
        texto = self._briefing()
        self.assertIn('orq-clickup set-status 868001 "revisão"', texto)
        # `comment` do orq-clickup é posicional — nunca "--text" (bug antigo
        # que mandava um comentário começando com a palavra "--text").
        self.assertNotIn("comment 868001 --text", texto)
        self.assertIn('orq-clickup comment 868001 "<URL do PR', texto)

    def test_encerramento_bloqueado_escreve_status_e_motivo(self):
        texto = self._briefing()
        self.assertIn('orq-clickup set-status 868001 "bloqueado"', texto)
        self.assertIn("AGUARDANDO DECISÃO HUMANA", texto)
        self.assertNotIn("comment 868001 --text", texto)

    def test_ordem_encerrar_antes_de_atualizar_o_cartao(self):
        texto = self._briefing()
        self.assertLess(texto.index("7. ENCERRE"), texto.index("8. SÓ DEPOIS"))


if __name__ == "__main__":
    unittest.main()
