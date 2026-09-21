"""Testes do vigia de PR e do laço autônomo (OA-08).

Duas camadas, como o resto da suíte:
  * MÓDULO — bin/orq carregado via SourceFileLoader (mesmo padrão de
    test_maquina.py), testando `vigiar_prs`, `_concluir_merge`,
    `encerramento_fixo` (nomes canônicos), `_trabalho_vivo` e
    `_intervalo_efetivo` diretamente.
  * PROCESSO — bin/orq como subprocesso, provando que `orq tick`,
    `orq advance --forcar` e `orq loop` estão de fato religados.

Todo teste fala com um `gh` de mentira (testes/fixtures/bin/gh) que entende
tanto a checagem simples de `_pr_existe` (OA-05) quanto o `--json` que o
vigia usa (OA-08) — nenhum teste aqui toca a API real do GitHub.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORQ_BIN = RAIZ / "bin" / "orq"
FAKE_GH = RAIZ / "testes" / "fixtures" / "bin"

_loader = importlib.machinery.SourceFileLoader("orq", str(ORQ_BIN))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


# ==================================================================== MÓDULO

class ComUnidadeEmRevisao(unittest.TestCase):
    """FE-A em 'revisao' com PR #101; FE-B em 'backlog' dependendo de FE-A —
    o par que toda transição do vigia precisa provar (a transição em si, e a
    liberação do dependente no mesmo ciclo)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        self.b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        orq.adicionar_dependencia(con, self.b, self.a)
        con.execute("INSERT INTO config (chave, valor) VALUES ('github_repo', 'acme/x')")
        con.commit()
        with orq.transacao(self.caminho) as con2:
            orq.transicionar(con2, self.a, "em_progresso")
            orq.transicionar(con2, self.a, "revisao")
            con2.execute("UPDATE unidade SET pr_numero = 101 WHERE id = ?", (self.a,))
        con.close()

        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_GH}:{self._path_original}"
        for k in list(os.environ):
            if k.startswith("FAKE_GH"):
                del os.environ[k]
        os.environ["FAKE_GH_PRS_OK"] = "*"

    def tearDown(self):
        os.environ["PATH"] = self._path_original
        for k in list(os.environ):
            if k.startswith("FAKE_GH"):
                del os.environ[k]
        self.tmp.cleanup()

    def _github_repo(self):
        con = orq.abrir_banco(self.caminho)
        v = orq.obter_config(con, "github_repo")
        con.close()
        return v

    def _status(self, uid):
        con = orq.abrir_banco(self.caminho)
        row = con.execute("SELECT status FROM unidade WHERE id = ?", (uid,)).fetchone()
        con.close()
        return row["status"]


class MergeViraPronto(ComUnidadeEmRevisao):
    def test_merge_vira_pronto_e_libera_dependente_no_mesmo_ciclo(self):
        os.environ["FAKE_GH_PR_STATE_101"] = "MERGED"
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "pronto")
        self.assertEqual([a["desfecho"] for a in achados], ["pronto"])

        con = orq.abrir_banco(self.caminho)
        prontas = {u["chave"] for u in orq.unidades_prontas(con)}
        con.close()
        self.assertIn("FE-B", prontas)   # liberada no MESMO ciclo, sem esperar outro tick

    def test_evento_pr_fundido_e_gravado(self):
        os.environ["FAKE_GH_PR_STATE_101"] = "MERGED"
        with orq.transacao(self.caminho) as con:
            orq.vigiar_prs(con, self._github_repo())
        con = orq.abrir_banco(self.caminho)
        ev = con.execute(
            "SELECT de_status, para_status FROM evento WHERE unidade_id = ? "
            "AND tipo = 'pr_fundido'", (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)
        self.assertEqual((ev["de_status"], ev["para_status"]), ("revisao", "pronto"))


class ChangesRequestedVoltaParaEmProgresso(ComUnidadeEmRevisao):
    def test_devolve_para_em_progresso(self):
        os.environ["FAKE_GH_PR_REVIEW_101"] = "CHANGES_REQUESTED"
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "em_progresso")
        self.assertEqual(achados[0]["desfecho"], "em_progresso")


class PrFechadoSemMergeBloqueia(ComUnidadeEmRevisao):
    def test_bloqueia_com_motivo_legivel(self):
        os.environ["FAKE_GH_PR_STATE_101"] = "CLOSED"
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "bloqueado")
        self.assertEqual(achados[0]["desfecho"], "bloqueado")
        con = orq.abrir_banco(self.caminho)
        motivo = con.execute(
            "SELECT motivo FROM unidade WHERE id = ?", (self.a,)).fetchone()["motivo"]
        con.close()
        self.assertIn("fechado", motivo.lower())


class PrAbertoSemNovidade(ComUnidadeEmRevisao):
    def test_nao_muda_nada(self):
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "revisao")
        self.assertEqual(achados, [])


class PrRascunho(ComUnidadeEmRevisao):
    def test_rascunho_nao_conta_como_revisao_pedida_e_aparece_no_quadro(self):
        os.environ["FAKE_GH_PR_DRAFT_101"] = "1"
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "revisao")
        self.assertEqual(achados[0]["desfecho"], "rascunho")

        con = orq.abrir_banco(self.caminho)
        linhas = orq.classificar(con)
        con.close()
        linha_a = next(l for l in linhas if l["unidade"]["chave"] == "FE-A")
        self.assertIn("rascunho", linha_a["motivo"])


class ErroDoGhNuncaMoveUnidade(ComUnidadeEmRevisao):
    def test_falha_isolada_nao_move_e_registra_evento(self):
        os.environ["FAKE_GH_PR_FAIL_101"] = "1"
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "revisao")
        self.assertEqual(achados[0]["desfecho"], "falhou")

        con = orq.abrir_banco(self.caminho)
        n = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'vigia_falhou'",
            (self.a,)).fetchone()[0]
        falhas = con.execute(
            "SELECT vigia_falhas FROM unidade WHERE id = ?", (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(n, 1)
        self.assertEqual(falhas, 1)

    def test_tres_falhas_seguidas_escalam_um_unico_alerta(self):
        os.environ["FAKE_GH_PR_FAIL_101"] = "1"
        for _ in range(4):
            with orq.transacao(self.caminho) as con:
                orq.vigiar_prs(con, self._github_repo())
        con = orq.abrir_banco(self.caminho)
        falhas = con.execute(
            "SELECT vigia_falhas FROM unidade WHERE id = ?", (self.a,)).fetchone()[0]
        n_alertas = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'vigia_alerta'",
            (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(falhas, 4)
        self.assertEqual(n_alertas, 1)   # só escala na 3a — não repete a cada ciclo

    def test_gh_fora_da_path_tambem_nao_move_nada(self):
        os.environ["PATH"] = self._path_original   # tira o gh de mentira da PATH
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, self._github_repo())
        self.assertEqual(self._status(self.a), "revisao")
        self.assertEqual(achados[0]["desfecho"], "falhou")

    def test_sucesso_depois_de_falha_zera_o_contador(self):
        os.environ["FAKE_GH_PR_FAIL_101"] = "1"
        with orq.transacao(self.caminho) as con:
            orq.vigiar_prs(con, self._github_repo())
        del os.environ["FAKE_GH_PR_FAIL_101"]
        with orq.transacao(self.caminho) as con:
            orq.vigiar_prs(con, self._github_repo())
        con = orq.abrir_banco(self.caminho)
        falhas = con.execute(
            "SELECT vigia_falhas FROM unidade WHERE id = ?", (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(falhas, 0)


class ConcluirMerge(unittest.TestCase):
    """`_concluir_merge` roda FORA de qualquer transação — teardown, evento,
    artefatos, remoção de worktree/branch, sempre nesta ordem."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.commit()
        con.close()
        self._state_original = orq.STATE
        orq.STATE = Path(self.tmp.name) / "state"
        orq.STATE.mkdir()

    def tearDown(self):
        orq.STATE = self._state_original
        self.tmp.cleanup()

    def test_sem_compose_teardown_ok_antes_do_arquivamento(self):
        wt = Path(self.tmp.name) / "wt"
        wt.mkdir()
        achado = {"unidade_id": self.a, "chave": "FE-A", "worktree": str(wt), "branch": "b"}
        resultado = orq._concluir_merge(self.caminho, None, "esteira", achado)
        self.assertIn("pronto", resultado)

        con = orq.abrir_banco(self.caminho)
        ev = con.execute(
            "SELECT ts FROM evento WHERE unidade_id = ? AND tipo = 'teardown_ok'",
            (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)

        meta_path = next((orq.STATE / "archive").rglob("meta.json"))
        meta = json.loads(meta_path.read_text())
        self.assertLessEqual(ev["ts"], meta["arquivado_em"])

    def test_teardown_falho_preserva_a_worktree(self):
        wt = Path(self.tmp.name) / "wt2"
        wt.mkdir()
        achado = {"unidade_id": self.a, "chave": "FE-A", "worktree": str(wt), "branch": "b"}
        with unittest.mock.patch.object(
                orq, "encerramento_fixo", return_value=["docker down falhou"]):
            resultado = orq._concluir_merge(self.caminho, str(self.tmp.name), "esteira", achado)
        self.assertIn("NÃO removida", resultado)
        self.assertTrue(wt.exists())

        con = orq.abrir_banco(self.caminho)
        ev = con.execute(
            "SELECT texto FROM evento WHERE unidade_id = ? AND tipo = 'teardown_falhou'",
            (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)
        self.assertIn("docker down falhou", ev["texto"])

    def test_sem_worktree_registrada_nao_quebra(self):
        achado = {"unidade_id": self.a, "chave": "FE-A", "worktree": None, "branch": None}
        resultado = orq._concluir_merge(self.caminho, None, "esteira", achado)
        self.assertIn("pronto", resultado)


class EncerramentoFixoNomesCanonicos(unittest.TestCase):
    def test_acha_compose_yaml_docker_compose_yml_e_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp)
            for nome in ("compose.yaml", "docker-compose.yml", "docker-compose.override.yml"):
                (wt / nome).write_text("services: {}\n")
            chamados = []

            def fake_run(args, **kwargs):
                chamados.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with unittest.mock.patch.object(orq.subprocess, "run", side_effect=fake_run):
                falhas = orq.encerramento_fixo(wt)
            self.assertEqual(falhas, [])
            nomes = {Path(c[c.index("-f") + 1]).name for c in chamados}
            self.assertEqual(
                nomes, {"compose.yaml", "docker-compose.yml", "docker-compose.override.yml"})


class TrabalhoVivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_nada_vivo_e_falso(self):
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq._trabalho_vivo(con))
        con.close()

    def test_unidade_em_revisao_conta_como_vivo(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "revisao")
        con = orq.abrir_banco(self.caminho)
        self.assertTrue(orq._trabalho_vivo(con))
        con.close()

    def test_sessao_viva_conta_como_vivo(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.registrar_sessao(con, self.a, worktree="/tmp/w", branch="b", pid=os.getpid())
        con = orq.abrir_banco(self.caminho)
        self.assertTrue(orq._trabalho_vivo(con))
        con.close()


class IntervaloEfetivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        orq.criar_banco(self.caminho).close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sem_config_e_sem_flag_usa_60(self):
        con = orq.abrir_banco(self.caminho)
        self.assertEqual(orq._intervalo_efetivo(con, None), 60)
        con.close()

    def test_config_declarada_vence_o_padrao(self):
        with orq.transacao(self.caminho) as con:
            orq.definir_config(con, "interval_seconds", "45")
        con = orq.abrir_banco(self.caminho)
        self.assertEqual(orq._intervalo_efetivo(con, None), 45)
        con.close()

    def test_flag_explicita_vence_tudo_inclusive_zero(self):
        with orq.transacao(self.caminho) as con:
            orq.definir_config(con, "interval_seconds", "45")
        con = orq.abrir_banco(self.caminho)
        self.assertEqual(orq._intervalo_efetivo(con, 5), 5)
        self.assertEqual(orq._intervalo_efetivo(con, 0), 0)
        con.close()


# =================================================================== PROCESSO

def orq_cli(db, *args, cwd=None, checar=True, env_extra=None):
    # `gh` de mentira na PATH (testes/fixtures/bin/gh): nenhum teste aqui
    # fala com a API real do GitHub.
    env = {**os.environ, "PATH": f"{FAKE_GH}:{os.environ.get('PATH', '')}",
          "FAKE_GH_PRS_OK": "*", **(env_extra or {})}
    r = subprocess.run(
        [sys.executable, str(ORQ_BIN), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(
            f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class TickEAdvanceComoSubprocesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "e.db"
        con = orq.criar_banco(self.db)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        self.b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        con.execute("INSERT INTO config (chave, valor) VALUES ('github_repo', 'acme/x')")
        con.commit()
        con.close()
        with orq.transacao(self.db) as con:
            orq.adicionar_dependencia(con, self.b, self.a)
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "revisao")
            con.execute("UPDATE unidade SET pr_numero = 9 WHERE id = ?", (self.a,))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tick_funde_e_libera_dependente_no_mesmo_tick(self):
        r = orq_cli(self.db, "tick", env_extra={"FAKE_GH_PR_STATE_9": "MERGED"})
        self.assertIn("pronto", r.stdout)
        rb = orq_cli(self.db, "board")
        linhas = {l.split()[1]: l for l in rb.stdout.splitlines()}
        self.assertIn("pronto", linhas["FE-A"])
        self.assertIn("backlog", linhas["FE-B"])   # liberada

    def test_tick_com_gh_fora_do_ar_nao_move_nada(self):
        r = orq_cli(self.db, "tick", env_extra={"FAKE_GH_FAIL_ALL": "1"})
        self.assertIn("vigia falhou", r.stdout)
        con = orq.abrir_banco(self.db)
        status = con.execute(
            "SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        con.close()
        self.assertEqual(status, "revisao")

    def test_orq_advance_forcar_fecha_revisao_fundida_fora_do_fluxo(self):
        r = orq_cli(self.db, "advance", "FE-A", "--forcar")
        self.assertIn("pronto", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute(
            "SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()
        ev = con.execute(
            "SELECT tipo FROM evento WHERE unidade_id = ? AND tipo = 'pr_fundido_manual'",
            (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "pronto")
        self.assertIsNotNone(ev)

    def test_orq_advance_forcar_fora_de_revisao_recusa(self):
        r = orq_cli(self.db, "advance", "FE-B", "--forcar", checar=False)   # FE-B está em backlog
        self.assertNotEqual(r.returncode, 0)

    def test_advance_sem_pr_e_sem_forcar_recusa(self):
        r = orq_cli(self.db, "advance", "FE-A", checar=False)
        self.assertNotEqual(r.returncode, 0)


class LoopComoSubprocesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "loop.db"
        orq.criar_banco(self.db).close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_esteira_vazia_para_apos_vinte_ciclos_ociosos(self):
        r = orq_cli(self.db, "loop", "--interval", "0")
        self.assertIn("ciclos sem nada vivo", r.stdout)
        con = orq.abrir_banco(self.db)
        ev = con.execute("SELECT texto FROM evento WHERE tipo = 'laco_parado'").fetchone()
        con.close()
        self.assertIsNotNone(ev)
        self.assertIn("20", ev["texto"])


if __name__ == "__main__":
    unittest.main()
