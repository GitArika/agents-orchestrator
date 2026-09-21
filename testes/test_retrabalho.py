"""Testes do retrabalho a partir do PR (OA-09).

Duas camadas:
  * MÓDULO — bin/orq carregado via SourceFileLoader, testando
    `_atualizar_worktree_ou_falhar`, `_coletar_retrabalho`,
    `_formatar_bloco_retrabalho` e `_relancar_retrabalho` diretamente, com um
    repositório git de verdade (mesmo padrão de test_lancador.py), um `gh`
    de mentira (testes/fixtures/bin/gh) e um `claude` de mentira
    (testes/fixtures/bin/claude, dorme sem fazer nada) — nenhum teste aqui
    fala com o GitHub real nem sobe uma sessão de verdade.
  * PROCESSO — `orq release --zerar-retrabalho` como subprocesso.

A detecção (revisão devolvida → em_progresso, e o teto → bloqueado) é
`vigiar_prs` (OA-08); aqui o que se testa é o que ACONTECE depois disso —
montar o escopo, relançar na mesma worktree, o teto, o zerar do contador.
"""
import datetime
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

# `orq-avisar` de mentira (OA-11): nenhum teste deste arquivo entrega aviso
# de verdade, mesmo que a máquina tenha credenciais reais configuradas — o
# teto e o release geram eventos roteados (bloqueada).
os.environ.setdefault("ORQ_NOTIFY_CMD", str(FAKE_BIN / "orq-avisar"))

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


def _depois(iso: str, minutos: int = 1) -> str:
    dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    return (dt + datetime.timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==================================================================== MÓDULO

class AtualizarWorktreeOuFalhar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        r = _git(self.repo, "worktree", "add", "-b", "feature", str(self.raiz / "wt"))
        self.wt = self.raiz / "wt"

    def tearDown(self):
        self.tmp.cleanup()

    def test_avanco_em_linha_reta_passa_sem_erro(self):
        (self.repo / "novo.txt").write_text("x")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "avanco na base")
        erro = orq._atualizar_worktree_ou_falhar(self.repo, self.wt, "main")
        self.assertIsNone(erro)
        self.assertTrue((self.wt / "novo.txt").exists())

    def test_divergencia_de_verdade_falha_com_mensagem(self):
        (self.wt / "local.txt").write_text("mudanca local nao publicada")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-q", "-m", "mudanca local")
        (self.repo / "outro.txt").write_text("mudanca na base")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "avanco na base")
        erro = orq._atualizar_worktree_ou_falhar(self.repo, self.wt, "main")
        self.assertIsNotNone(erro)


class ColetarRetrabalho(unittest.TestCase):
    def setUp(self):
        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_BIN}:{self._path_original}"
        for k in list(os.environ):
            if k.startswith("FAKE_GH_PR_"):
                del os.environ[k]

    def tearDown(self):
        os.environ["PATH"] = self._path_original
        for k in list(os.environ):
            if k.startswith("FAKE_GH_PR_"):
                del os.environ[k]

    def test_filtra_reviews_e_comentarios_por_data(self):
        os.environ["FAKE_GH_PR_REVIEWS_9"] = json.dumps([
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2020-01-01T00:00:00Z", "body": "velha"},
            {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2026-06-01T00:00:00Z", "body": "nova"},
            {"author": {"login": "carol"}, "state": "APPROVED",
             "submittedAt": "2026-06-02T00:00:00Z", "body": "aprovado, ignorar"},
        ])
        os.environ["FAKE_GH_PR_COMMENTS_9"] = json.dumps([
            {"path": "a.py", "line": 1, "body": "velho", "created_at": "2020-01-01T00:00:00Z"},
            {"path": "b.py", "line": 2, "body": "novo", "created_at": "2026-06-01T00:00:00Z"},
        ])
        colhido = orq._coletar_retrabalho("acme/x", 9, "2025-01-01T00:00:00Z")
        self.assertEqual(len(colhido["reviews"]), 1)
        self.assertEqual(colhido["reviews"][0]["body"], "nova")
        self.assertEqual(len(colhido["comentarios"]), 1)
        self.assertEqual(colhido["comentarios"][0]["body"], "novo")

    def test_sem_desde_traz_tudo(self):
        os.environ["FAKE_GH_PR_REVIEWS_9"] = json.dumps([
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2020-01-01T00:00:00Z", "body": "unica"}])
        colhido = orq._coletar_retrabalho("acme/x", 9, None)
        self.assertEqual(len(colhido["reviews"]), 1)

    def test_gh_fora_do_ar_nao_quebra_devolve_vazio(self):
        os.environ["FAKE_GH_FAIL_ALL"] = "1"
        colhido = orq._coletar_retrabalho("acme/x", 9, None)
        os.environ.pop("FAKE_GH_FAIL_ALL", None)
        self.assertEqual(colhido, {"reviews": [], "comentarios": []})


class FormatarBlocoRetrabalho(unittest.TestCase):
    def test_inclui_numeracao_autor_data_corpo_e_comentarios(self):
        colhido = {
            "reviews": [{"author": {"login": "alice"}, "submittedAt": "2026-06-01T10:00:00Z",
                        "body": "ajuste o tratamento de erro"}],
            "comentarios": [{"path": "bin/orq", "line": 42, "body": "isto vaza credencial"}],
        }
        bloco = orq._formatar_bloco_retrabalho(1, 2, 9, colhido)
        self.assertIn("RETRABALHO 1/2", bloco)
        self.assertIn("alice", bloco)
        self.assertIn("2026-06-01", bloco)
        self.assertIn("ajuste o tratamento de erro", bloco)
        self.assertIn("bin/orq:42", bloco)
        self.assertIn("isto vaza credencial", bloco)
        self.assertIn("#9", bloco)
        self.assertIn("NÃO abra outro PR", bloco)

    def test_sem_review_nem_comentario_nao_quebra(self):
        bloco = orq._formatar_bloco_retrabalho(1, 2, 9, {"reviews": [], "comentarios": []})
        self.assertIn("RETRABALHO 1/2", bloco)
        self.assertIn("(nenhum)", bloco)


class ComWorktreeEClaudeDeMentira(unittest.TestCase):
    """FE-01 com uma worktree JÁ existente (como fica depois de `orq
    advance` — a worktree sobrevive à revisão) e um `claude` de mentira na
    PATH: a base para todo teste de `_relancar_retrabalho`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.worktrees = self.raiz / "worktrees"
        self.worktrees.mkdir()
        self.db = self.raiz / "e.db"
        con = orq.criar_banco(self.db)
        # `repo` RESOLVIDO — mesma escolha de `cmd_init` (segue symlink;
        # no macOS /tmp é symlink para /private/tmp), senão a chave de
        # confiança de `ensure_trusted` nunca bate.
        for chave, valor in {
            "name": "esteira", "repo": str(self.repo.resolve()), "base_branch": "main",
            "worktree_root": str(self.worktrees), "github_repo": "acme/x",
        }.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        self.uid = orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="a")
        con.commit()
        con.close()

        with orq.transacao(self.db) as con:
            orq.transicionar(con, self.uid, "em_progresso")
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT * FROM unidade WHERE id = ?", (self.uid,)).fetchone()
        self.wt, self.branch = orq.ensure_worktree(con, u)
        con.close()

        self.claude_json = self.raiz / "claude.json"
        self.claude_json.write_text(json.dumps(
            {"projects": {str(self.repo.resolve()): {"hasTrustDialogAccepted": True}}}))
        self._claude_json_original = orq.CLAUDE_JSON
        orq.CLAUDE_JSON = self.claude_json

        self._state_original = orq.STATE
        orq.STATE = self.raiz / "state"
        orq.STATE.mkdir()

        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_BIN}:{self._path_original}"
        os.environ["FAKE_CLAUDE_SLEEP"] = "20"
        os.environ["FAKE_GH_PRS_OK"] = "*"
        for k in list(os.environ):
            if k.startswith("FAKE_GH_PR_"):
                del os.environ[k]

    def tearDown(self):
        subprocess.run(["tmux", "kill-session", "-t", "orq-esteira-FE-01"],
                       capture_output=True)
        orq.CLAUDE_JSON = self._claude_json_original
        orq.STATE = self._state_original
        os.environ["PATH"] = self._path_original
        for k in list(os.environ):
            if k.startswith("FAKE_GH_PR_") or k in ("FAKE_CLAUDE_SLEEP", "FAKE_GH_PRS_OK"):
                del os.environ[k]
        self.tmp.cleanup()

    def _achado(self, retrabalho=0, retrabalho_em=None, pr_numero=9):
        return {"chave": "FE-01", "desfecho": "em_progresso", "unidade_id": self.uid,
               "pr_numero": pr_numero, "retrabalho": retrabalho,
               "retrabalho_em": retrabalho_em, "worktree": str(self.wt), "branch": self.branch}

    def _brief(self):
        return (orq.STATE / f"esteira-{self.uid}.brief.md").read_text()


class RelancaComEscopoCerto(ComWorktreeEClaudeDeMentira):
    def test_briefing_contem_corpo_da_review_e_comentarios_de_linha(self):
        os.environ["FAKE_GH_PR_REVIEWS_9"] = json.dumps([
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2020-01-01T00:00:00Z", "body": "ajuste o tratamento de erro"}])
        os.environ["FAKE_GH_PR_COMMENTS_9"] = json.dumps([
            {"path": "bin/orq", "line": 42, "body": "isto vaza credencial",
             "created_at": "2020-01-01T00:00:00Z"}])
        resultado = orq._relancar_retrabalho(self.db, "acme/x", str(self.repo), self._achado())
        self.assertIn("retrabalho 1/2 relançado", resultado)

        brief = self._brief()
        self.assertTrue(brief.startswith("RETRABALHO 1/2"))
        self.assertIn("ajuste o tratamento de erro", brief)
        self.assertIn("bin/orq:42", brief)
        self.assertIn("isto vaza credencial", brief)
        self.assertIn("alice", brief)
        # o resto do briefing normal (OA-05) continua vindo junto, depois do bloco
        self.assertIn("Um papel só", brief)
        self.assertIn("FE-01", brief)

        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT retrabalho, retrabalho_em, pr_numero FROM unidade "
                        "WHERE id = ?", (self.uid,)).fetchone()
        con.close()
        self.assertEqual(u["retrabalho"], 1)
        self.assertIsNotNone(u["retrabalho_em"])


class NaoRepeteAchadoJaCorrigido(ComWorktreeEClaudeDeMentira):
    def test_segundo_briefing_contem_so_a_segunda_rodada(self):
        os.environ["FAKE_GH_PR_REVIEWS_9"] = json.dumps([
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2020-01-01T00:00:00Z", "body": "PRIMEIRA RODADA"}])
        orq._relancar_retrabalho(self.db, "acme/x", str(self.repo), self._achado())

        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT retrabalho, retrabalho_em FROM unidade WHERE id = ?",
                        (self.uid,)).fetchone()
        con.close()

        segunda_data = _depois(u["retrabalho_em"])
        os.environ["FAKE_GH_PR_REVIEWS_9"] = json.dumps([
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED",
             "submittedAt": "2020-01-01T00:00:00Z", "body": "PRIMEIRA RODADA"},
            {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED",
             "submittedAt": segunda_data, "body": "SEGUNDA RODADA"}])
        achado2 = self._achado(retrabalho=u["retrabalho"], retrabalho_em=u["retrabalho_em"])
        orq._relancar_retrabalho(self.db, "acme/x", str(self.repo), achado2)

        brief = self._brief()
        self.assertIn("SEGUNDA RODADA", brief)
        self.assertNotIn("PRIMEIRA RODADA", brief)


class RelancaNaMesmaWorktreeENoMesmoPr(ComWorktreeEClaudeDeMentira):
    def test_worktree_branch_e_pr_identicos_com_sessao_nova(self):
        (self.wt / "marca.txt").write_text("progresso da 1a rodada")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-q", "-m", "progresso da 1a rodada")
        with orq.transacao(self.db) as con:
            con.execute("UPDATE unidade SET pr_numero = 9 WHERE id = ?", (self.uid,))

        orq._relancar_retrabalho(self.db, "acme/x", str(self.repo), self._achado(pr_numero=9))

        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT pr_numero FROM unidade WHERE id = ?", (self.uid,)).fetchone()
        sess = con.execute(
            "SELECT worktree, branch, tmux FROM sessao WHERE unidade_id = ? "
            "ORDER BY id DESC LIMIT 1", (self.uid,)).fetchone()
        con.close()
        self.assertEqual(u["pr_numero"], 9)   # relançar nunca mexe no PR
        self.assertEqual(Path(sess["worktree"]), self.wt)
        self.assertEqual(sess["branch"], self.branch)
        self.assertEqual(sess["tmux"], "orq-esteira-FE-01")
        self.assertTrue((self.wt / "marca.txt").exists())   # commit da 1a rodada preservado


class BaseDivergidaBloqueiaAoInvesDeAdivinhar(ComWorktreeEClaudeDeMentira):
    def test_merge_nao_ff_bloqueia_com_motivo_citando_o_conflito(self):
        (self.wt / "local.txt").write_text("mudanca local nao publicada")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-q", "-m", "mudanca local")
        (self.repo / "outro.txt").write_text("mudanca na base")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "avanco na base")

        resultado = orq._relancar_retrabalho(self.db, "acme/x", str(self.repo), self._achado())
        self.assertIn("base divergiu", resultado)

        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, motivo FROM unidade WHERE id = ?",
                        (self.uid,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "bloqueado")
        self.assertIn("base divergiu", u["motivo"])


class TetoLevaABloqueado(unittest.TestCase):
    """O teto é checado DENTRO de `vigiar_prs` (OA-08) — nem chega a criar
    achado de retrabalho quando `max_rework` já foi atingido."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "t.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.execute("INSERT INTO config (chave, valor) VALUES ('github_repo', 'acme/x')")
        con.execute("INSERT INTO config (chave, valor) VALUES ('max_rework', '2')")
        con.commit()
        con.close()
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "revisao")
            con.execute("UPDATE unidade SET pr_numero = 9, retrabalho = 2 WHERE id = ?",
                       (self.a,))
        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_BIN}:{self._path_original}"
        os.environ["FAKE_GH_PR_REVIEW_9"] = "CHANGES_REQUESTED"

    def tearDown(self):
        os.environ["PATH"] = self._path_original
        os.environ.pop("FAKE_GH_PR_REVIEW_9", None)
        self.tmp.cleanup()

    def test_terceira_devolucao_bloqueia_com_motivo_sobre_o_requisito(self):
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, "acme/x")
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["chave"], "FE-A")
        self.assertEqual(achados[0]["desfecho"], "bloqueado")
        self.assertIn("requisito", achados[0]["motivo"])
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT status, motivo FROM unidade WHERE id = ?",
                        (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "bloqueado")
        self.assertIn("requisito", u["motivo"])

    def test_abaixo_do_teto_relanca_em_vez_de_bloquear(self):
        con = orq.abrir_banco(self.caminho)
        con.execute("UPDATE unidade SET retrabalho = 1 WHERE id = ?", (self.a,))
        con.commit()
        con.close()
        with orq.transacao(self.caminho) as con:
            achados = orq.vigiar_prs(con, "acme/x")
        self.assertEqual(achados[0]["desfecho"], "em_progresso")
        self.assertEqual(achados[0]["retrabalho"], 1)


# =================================================================== PROCESSO

def orq_cli(db, *args, cwd=None, checar=True, env_extra=None):
    env = {**os.environ, "ORQ_NOTIFY_CMD": str(FAKE_BIN / "orq-avisar"), **(env_extra or {})}
    r = subprocess.run(
        [sys.executable, str(ORQ_BIN), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(
            f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class ZerarRetrabalho(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        con = orq.criar_banco(self.db)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.commit()
        con.close()
        with orq.transacao(self.db) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "bloqueado", tipo_evento="bloqueada", motivo="teto")
            con.execute("UPDATE unidade SET retrabalho = 2, retrabalho_em = ? WHERE id = ?",
                       (orq._agora(), self.a))

    def tearDown(self):
        self.tmp.cleanup()

    def test_zerar_retrabalho_reseta_o_contador_e_libera(self):
        r = orq_cli(self.db, "release", "FE-A", "--zerar-retrabalho")
        self.assertIn("retrabalho zerado", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, retrabalho, retrabalho_em FROM unidade "
                        "WHERE id = ?", (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["retrabalho"], 0)
        self.assertIsNone(u["retrabalho_em"])

    def test_release_sem_a_flag_preserva_o_contador(self):
        orq_cli(self.db, "release", "FE-A")
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT retrabalho FROM unidade WHERE id = ?", (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["retrabalho"], 2)


if __name__ == "__main__":
    unittest.main()
