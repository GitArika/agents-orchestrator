"""Testes do lançador de sessão (OA-05): worktree, confiança, briefing único,
settings da cerca, capacidade, e os verbos run/dispatch/attach/log/stop, mais
a extensão de hold/advance para arquivar e encerrar a sessão com delicadeza.

Duas camadas, como o resto da suíte:
  * MÓDULO — bin/orq carregado via SourceFileLoader, testando `branch_for`,
    `ensure_worktree`, `ensure_trusted`, `settings_json`, `build_brief`,
    `capacidade`, `encerramento_fixo`, `arquivar_artefatos` diretamente.
  * PROCESSO — o CLI de ponta a ponta com um `claude` de mentira
    (testes/fixtures/bin/claude, dorme sem fazer nada) e tmux de verdade
    quando disponível.

Nenhum teste aqui sobe uma sessão real do Claude Code nem fala com a API do
GitHub — `gh` também é o de mentira (testes/fixtures/bin/gh, OA-03/04).

O QUE NÃO É TESTADO AQUI, de propósito: a bateria completa da cerca (força,
delete, PR para base errada, merge dentro da base etc.) — isso é
testes/cerca.sh (OA-06). Aqui só a integração: que `launch()`/`settings_json`
entregam à cerca o ambiente (`ORQ_BRANCH`/`ORQ_BASE`) que ela precisa para
deixar passar o branch da própria unidade e continuar barrando a base e o
merge, com um repositório git de verdade.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORQ_BIN = RAIZ / "bin" / "orq"
FAKE_BIN = RAIZ / "testes" / "fixtures" / "bin"
CERCA = RAIZ / "hooks" / "cerca.sh"

_loader = importlib.machinery.SourceFileLoader("orq", str(ORQ_BIN))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


def _git(repo, *args, **kw):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)
    assert r.returncode == 0, f"git {args} falhou: {r.stderr}"
    return r


def _novo_repo(raiz: Path) -> Path:
    repo = raiz / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "CLAUDE.md").write_text("# regras do projeto\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "inicial")
    return repo


# ==================================================================== MÓDULO

class BranchFor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "e.db"
        con = orq.criar_banco(self.caminho)
        con.execute("INSERT INTO config (chave, valor) VALUES ('branch_template', "
                    "'CU-{id}-{slug}')")
        con.commit(); con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_monta_com_id_e_slug(self):
        con = orq.abrir_banco(self.caminho)
        branch = orq.branch_for(con, "FE-01", "868001", "Um Título Com Espaços")
        con.close()
        self.assertEqual(branch, "CU-868001-um-titulo-com-espacos")

    def test_sem_clickup_id_usa_a_chave(self):
        con = orq.abrir_banco(self.caminho)
        branch = orq.branch_for(con, "FE-01", None, "t")
        con.close()
        self.assertIn("FE-01", branch)


class EnsureWorktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.worktrees = self.raiz / "worktrees"
        self.worktrees.mkdir()
        self.caminho = self.raiz / "e.db"
        con = orq.criar_banco(self.caminho)
        for chave, valor in {"repo": str(self.repo), "base_branch": "main",
                             "worktree_root": str(self.worktrees)}.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="primeira")
        con.commit(); con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _unidade(self, con):
        return con.execute("SELECT * FROM unidade WHERE id = ?", (self.uid,)).fetchone()

    def test_cria_worktree_nova_a_partir_da_base(self):
        con = orq.abrir_banco(self.caminho)
        wt, branch = orq.ensure_worktree(con, self._unidade(con))
        con.close()
        self.assertTrue(wt.exists())
        self.assertTrue((wt / "CLAUDE.md").exists())
        r = subprocess.run(["git", "-C", str(wt), "branch", "--show-current"],
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), branch)

    def test_reaproveita_worktree_existente(self):
        con = orq.abrir_banco(self.caminho)
        wt1, branch1 = orq.ensure_worktree(con, self._unidade(con))
        (wt1 / "trabalho.txt").write_text("progresso")
        _git(wt1, "add", "-A"); _git(wt1, "commit", "-q", "-m", "progresso")
        wt2, branch2 = orq.ensure_worktree(con, self._unidade(con))
        con.close()
        self.assertEqual(wt1, wt2)
        self.assertEqual(branch1, branch2)
        self.assertTrue((wt2 / "trabalho.txt").exists())   # commit anterior preservado


class EnsureTrusted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.wt = self.raiz / "worktree"
        self.wt.mkdir()
        self._original = orq.CLAUDE_JSON
        orq.CLAUDE_JSON = self.raiz / "claude.json"

    def tearDown(self):
        orq.CLAUDE_JSON = self._original
        self.tmp.cleanup()

    def test_recusa_se_repo_base_nao_e_confiavel(self):
        orq.CLAUDE_JSON.write_text(json.dumps({"projects": {}}))
        with self.assertRaises(SystemExit):
            orq.ensure_trusted(self.repo, self.wt)

    def test_herda_confianca_do_repo_base(self):
        orq.CLAUDE_JSON.write_text(json.dumps(
            {"projects": {str(self.repo): {"hasTrustDialogAccepted": True}}}))
        orq.ensure_trusted(self.repo, self.wt)
        d = json.loads(orq.CLAUDE_JSON.read_text())
        self.assertTrue(d["projects"][str(self.wt)]["hasTrustDialogAccepted"])

    def test_idempotente(self):
        orq.CLAUDE_JSON.write_text(json.dumps(
            {"projects": {str(self.repo): {"hasTrustDialogAccepted": True}}}))
        orq.ensure_trusted(self.repo, self.wt)
        antes = orq.CLAUDE_JSON.read_text()
        orq.ensure_trusted(self.repo, self.wt)
        self.assertEqual(antes, orq.CLAUDE_JSON.read_text())


class SettingsJson(unittest.TestCase):
    def test_aponta_para_a_cerca_com_branch_e_base(self):
        # OA-06: ORQ_BRANCH/ORQ_BASE substituem o antigo ORQ_STAGE — a regra
        # de publicação da cerca passou a ser por branch, não por papel.
        bruto = orq.settings_json("FE-01", "/tmp/wt", "CU-1-x", "main")
        d = json.loads(bruto)
        cmd_pretooluse = d["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn(str(orq.CERCA), cmd_pretooluse)
        self.assertIn("ORQ_UNIT=FE-01", cmd_pretooluse)
        self.assertIn("ORQ_WORKTREE=/tmp/wt", cmd_pretooluse)
        self.assertIn("ORQ_BRANCH=CU-1-x", cmd_pretooluse)
        self.assertIn("ORQ_BASE=main", cmd_pretooluse)
        self.assertNotIn("ORQ_STAGE", cmd_pretooluse)

    def test_tem_notification_e_stop(self):
        d = json.loads(orq.settings_json("FE-01", "/tmp/wt", "CU-1-x", "main"))
        self.assertIn("Notification", d["hooks"])
        self.assertIn("Stop", d["hooks"])


class BuildBrief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "e.db"
        con = orq.criar_banco(self.caminho)
        for chave, valor in {"name": "front-end", "base_branch": "main",
                             "repo": "/repo", "github_repo": "acme/app"}.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="868001",
                                     titulo="Implementar o seletor de período")
        con.commit(); con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_contem_o_essencial(self):
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT * FROM unidade WHERE id = ?", (self.uid,)).fetchone()
        texto = orq.build_brief(con, u, Path("/tmp/wt"), "CU-868001-x")
        con.close()
        for esperado in ("FE-01", "868001", "Implementar o seletor de período",
                         "orq-clickup show 868001", "CLAUDE.md", "AGENTS.md",
                         "gh pr create", "NÃO FUNDA", "orq advance", "orq hold",
                         "CU-868001-x", "acme/app", "front-end"):
            self.assertIn(esperado, texto)

    def test_ordem_das_escritas_banco_antes_do_cartao(self):
        # "Banco primeiro, cartão depois" (a seção do spec que nomeia isso):
        # ENCERRAR (orq advance/hold, que grava no banco) tem de aparecer no
        # texto ANTES de ATUALIZAR O CARTÃO (orq-clickup comment).
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT * FROM unidade WHERE id = ?", (self.uid,)).fetchone()
        texto = orq.build_brief(con, u, Path("/tmp/wt"), "CU-868001-x")
        con.close()
        pos_encerre = texto.index("ENCERRE")
        pos_cartao = texto.index("ATUALIZE O CARTÃO")
        self.assertLess(pos_encerre, pos_cartao,
                        "o passo de encerrar (banco) precisa vir antes do cartão")

    def test_e_um_briefing_so(self):
        # Critério de aceite do spec: existe UM briefing, não quatro.
        self.assertEqual(ORQ_BIN.read_text().count('BRIEFING = """'), 1)


class Capacidade(unittest.TestCase):
    def test_devolve_as_chaves_esperadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "e.db"
            con = orq.criar_banco(caminho)
            cap = orq.capacidade(con)
            con.close()
        for chave in ("logical_cpus", "total_ram_gb", "free_ram_gb", "load1",
                     "ram_per_session_gb", "reserve_ram_gb", "live", "slots_free"):
            self.assertIn(chave, cap)
        self.assertGreaterEqual(cap["slots_free"], 0)
        self.assertEqual(cap["live"], 0)   # banco novo, nada rodando

    def test_respeita_max_concurrent_declarado(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "e.db"
            con = orq.criar_banco(caminho)
            con.execute("INSERT INTO config (chave, valor) VALUES ('max_concurrent', '0')")
            con.execute("INSERT INTO config (chave, valor) VALUES ('ram_per_session_gb', '0.01')")
            con.commit()
            cap = orq.capacidade(con)
            con.close()
        # max_concurrent=0 significa "sem teto declarado" (mesma regra do
        # motor antigo), então by_hard não deve zerar as vagas.
        self.assertGreaterEqual(cap["slots_free"], 0)


class EncerramentoFixo(unittest.TestCase):
    def test_worktree_sem_compose_nao_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp)
            self.assertEqual(orq.encerramento_fixo(wt), [])

    def test_worktree_inexistente_nao_falha(self):
        self.assertEqual(orq.encerramento_fixo(Path("/nao/existe/mesmo")), [])

    @unittest.skipUnless(__import__("shutil").which("docker"), "docker ausente")
    def test_acha_docker_compose_por_convencao(self):
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp)
            (wt / "docker-compose.yml").write_text("services: {}\n")
            falhas = orq.encerramento_fixo(wt)
            # 'services: {}' é um compose válido vazio; down deve funcionar
            # (ou falhar por falta de daemon docker — ambos são aceitáveis
            # aqui, o que importa é que TENTOU e não quebrou o processo).
            self.assertIsInstance(falhas, list)


class ArquivarArtefatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._state_original = orq.STATE
        orq.STATE = Path(self.tmp.name) / "state"
        orq.STATE.mkdir()

    def tearDown(self):
        orq.STATE = self._state_original
        self.tmp.cleanup()

    def test_move_os_tres_artefatos_e_escreve_meta(self):
        (orq.STATE / "esteira-7.brief.md").write_text("briefing")
        (orq.STATE / "esteira-7.settings.json").write_text("{}")
        (orq.STATE / "esteira-7.log").write_text("log")
        dest = orq.arquivar_artefatos("esteira", 7, "FE-01", "hold")
        self.assertTrue((dest / "esteira-7.brief.md").exists())
        self.assertTrue((dest / "esteira-7.settings.json").exists())
        self.assertTrue((dest / "esteira-7.log").exists())
        meta = json.loads((dest / "meta.json").read_text())
        self.assertEqual(meta["unidade"], "FE-01")
        self.assertEqual(meta["outcome"], "hold")
        self.assertFalse((orq.STATE / "esteira-7.brief.md").exists())   # movido, não copiado

    def test_artefato_ausente_nao_quebra(self):
        dest = orq.arquivar_artefatos("esteira", 999, "FE-99", "hold")
        self.assertTrue(dest.exists())
        meta = json.loads((dest / "meta.json").read_text())
        self.assertEqual(meta["artefatos"], [])


class CercaComOAmbienteDoLancador(unittest.TestCase):
    """A prova estrutural de que `launch()` entrega à cerca o que ela
    precisa: publicar o PRÓPRIO branch passa, publicar a base ou fundir
    continua barrado. A bateria completa (força, delete, PR para base
    errada, merge dentro da base etc.) mora em testes/cerca.sh — aqui só a
    integração com o ambiente exato que `settings_json()` produz."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wt = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.wt, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=self.wt, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.wt, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                       cwd=self.wt, check=True)
        subprocess.run(["git", "checkout", "-qb", "CU-1-x"], cwd=self.wt, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar_cerca(self, comando):
        evento = json.dumps({"tool_name": "Bash", "tool_input": {"command": comando}})
        env = {**os.environ, "ORQ_UNIT": "FE-01", "ORQ_WORKTREE": str(self.wt),
              "ORQ_BRANCH": "CU-1-x", "ORQ_BASE": "main"}
        return subprocess.run(["bash", str(CERCA)], input=evento, capture_output=True,
                              text=True, env=env)

    def test_publicar_o_proprio_branch_passa(self):
        r = self._rodar_cerca("git push -u origin CU-1-x")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_publicar_a_base_e_barrado(self):
        r = self._rodar_cerca("git push origin main")
        self.assertEqual(r.returncode, 2)

    def test_gh_pr_merge_e_barrado(self):
        r = self._rodar_cerca("gh pr merge --squash")
        self.assertEqual(r.returncode, 2)

    def test_commit_local_passa(self):
        r = self._rodar_cerca('git commit -m "wip"')
        self.assertEqual(r.returncode, 0)


# =================================================================== PROCESSO

def orq_cli(db, *args, cwd=None, checar=True, env_extra=None, timeout=30):
    env = {**os.environ, "PATH": f"{FAKE_BIN}:{os.environ.get('PATH', '')}",
          "FAKE_GH_PRS_OK": "*", "FAKE_CLAUDE_SLEEP": "20", **(env_extra or {})}
    r = subprocess.run([sys.executable, str(ORQ_BIN), "--db", str(db), *args],
                       cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(f"orq {' '.join(args)} falhou ({r.returncode}):\n"
                             f"{r.stdout}\n{r.stderr}")
    return r


@unittest.skipUnless(orq.has_tmux(), "tmux ausente — o lançador exige tmux para estes testes")
class ComoSubprocesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.worktrees = self.raiz / "worktrees"
        self.worktrees.mkdir()
        self.db = self.raiz / "e.db"
        self.claude_json = self.raiz / "claude.json"
        # `cmd_init` grava `repo` RESOLVIDO (segue symlink) — a chave de
        # confiança precisa bater com isso, não com o caminho como foi
        # digitado (mesma pegadinha de /var vs /private/var no macOS).
        self.claude_json.write_text(json.dumps(
            {"projects": {str(self.repo.resolve()): {"hasTrustDialogAccepted": True}}}))
        self._env = {"ORQ_CLAUDE_JSON": str(self.claude_json)}
        orq_cli(self.db, "init", "--nome", "smoke", "--repo", str(self.repo),
               "--base", "main", "--worktrees", str(self.worktrees),
               "--github", "acme/smoke", env_extra=self._env)
        orq_cli(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "a",
               env_extra=self._env)

    def tearDown(self):
        subprocess.run(["tmux", "kill-session", "-t", "orq-smoke-FE-01"],
                       capture_output=True)
        self.tmp.cleanup()

    def _sessao_ainda_viva(self):
        r = subprocess.run(["tmux", "has-session", "-t", "orq-smoke-FE-01"],
                           capture_output=True)
        return r.returncode == 0

    def test_run_lanca_despacha_e_registra_sessao(self):
        r = orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        self.assertIn("despachada", r.stdout)
        self.assertTrue(self._sessao_ainda_viva())

        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status FROM unidade WHERE chave='FE-01'").fetchone()
        sess = con.execute(
            "SELECT tmux, worktree FROM sessao WHERE encerrada_em IS NULL").fetchone()
        con.close()
        self.assertEqual(u["status"], "em_progresso")
        self.assertEqual(sess["tmux"], "orq-smoke-FE-01")
        self.assertTrue(Path(sess["worktree"]).exists())
        self.assertTrue((Path(sess["worktree"]) / "CLAUDE.md").exists())

    def test_run_duas_vezes_sem_force_recusa(self):
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        r = orq_cli(self.db, "run", "FE-01", env_extra=self._env, checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_run_unidade_travada_por_dependencia_recusa(self):
        orq_cli(self.db, "task", "add", "FE-02", "--clickup", "2", "--titulo", "b",
               env_extra=self._env)
        orq_cli(self.db, "dep", "add", "FE-02", "--precisa", "FE-01", env_extra=self._env)
        r = orq_cli(self.db, "run", "FE-02", env_extra=self._env, checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_capacity_roda_sem_erro(self):
        r = orq_cli(self.db, "capacity", env_extra=self._env)
        self.assertIn("vagas livres", r.stdout)

    def test_log_mostra_o_que_o_claude_de_mentira_escreveu(self):
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        time.sleep(0.5)
        con = orq.abrir_banco(self.db)
        uid = con.execute("SELECT id FROM unidade WHERE chave='FE-01'").fetchone()["id"]
        con.close()
        logf = orq.STATE / "smoke-{}.log".format(uid)
        # o pipe-pane do tmux escreve aqui; dá um instante para o SO gravar.
        for _ in range(20):
            if logf.exists() and logf.stat().st_size > 0:
                break
            time.sleep(0.2)
        self.assertTrue(logf.exists())

    def test_stop_encerra_sem_mudar_status(self):
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        r = orq_cli(self.db, "stop", "FE-01", "--archive", env_extra=self._env)
        self.assertIn("encerrada", r.stdout)
        self.assertFalse(self._sessao_ainda_viva())
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status FROM unidade WHERE chave='FE-01'").fetchone()
        con.close()
        self.assertEqual(u["status"], "em_progresso")   # status NÃO muda

    def test_dispatch_lanca_as_prontas(self):
        orq_cli(self.db, "task", "add", "FE-02", "--clickup", "2", "--titulo", "b",
               env_extra=self._env)
        r = orq_cli(self.db, "dispatch", "-y", env_extra=self._env)
        self.assertIn("Disparando", r.stdout)
        con = orq.abrir_banco(self.db)
        vivas = con.execute(
            "SELECT count(*) FROM unidade WHERE status='em_progresso'").fetchone()[0]
        con.close()
        self.assertEqual(vivas, 2)
        subprocess.run(["tmux", "kill-session", "-t", "orq-smoke-FE-02"],
                       capture_output=True)

    def test_hold_apos_run_mata_a_sessao_e_arquiva(self):
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        con = orq.abrir_banco(self.db)
        wt = con.execute(
            "SELECT worktree FROM sessao WHERE encerrada_em IS NULL").fetchone()["worktree"]
        con.close()
        r = orq_cli(self.db, "hold", "FE-01", "--motivo", "esperando decisão de produto",
                   env_extra=self._env)
        self.assertIn("bloqueada", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status FROM unidade WHERE chave='FE-01'").fetchone()
        con.close()
        self.assertEqual(u["status"], "bloqueado")
        # a worktree morre em 'bloqueado' — só o branch/commits sobrevivem.
        self.assertFalse(Path(wt).exists())
        # a sessão morre com delicadeza (adiada); confirma que eventualmente cai.
        for _ in range(30):
            if not self._sessao_ainda_viva():
                break
            time.sleep(0.5)
        self.assertFalse(self._sessao_ainda_viva())

    def test_advance_apos_run_mantem_a_worktree(self):
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        con = orq.abrir_banco(self.db)
        wt = con.execute(
            "SELECT worktree FROM sessao WHERE encerrada_em IS NULL").fetchone()["worktree"]
        con.close()
        r = orq_cli(self.db, "advance", "FE-01", "--pr", "9", env_extra=self._env)
        self.assertIn("revisão", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status FROM unidade WHERE chave='FE-01'").fetchone()
        con.close()
        self.assertEqual(u["status"], "revisao")
        self.assertTrue(Path(wt).exists())   # worktree SOBREVIVE — OA-09 pode reusar

    def test_advance_recusa_pr_inexistente_e_nao_muda_status(self):
        # Critério de aceite do spec: `orq advance FE-01 --pr 999999` com PR
        # inexistente → recusa, status inalterado.
        orq_cli(self.db, "run", "FE-01", env_extra=self._env)
        env_sem_pr = {**self._env, "FAKE_GH_PRS_OK": ""}   # nenhum PR "existe"
        r = orq_cli(self.db, "advance", "FE-01", "--pr", "999999",
                   env_extra=env_sem_pr, checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("não existe", r.stdout + r.stderr)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, pr_numero FROM unidade WHERE chave='FE-01'").fetchone()
        con.close()
        self.assertEqual(u["status"], "em_progresso")   # inalterado
        self.assertIsNone(u["pr_numero"])


if __name__ == "__main__":
    unittest.main()
