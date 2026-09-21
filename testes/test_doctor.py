"""Testes do pré-voo (OA-12): `orq doctor` — cada prova por chamada real.

Duas camadas:
  * MÓDULO — bin/orq carregado via SourceFileLoader, testando cada
    `_prova_*` diretamente: mais rápido, e cada teste prova exatamente UMA
    coisa (o que um teste de `orq doctor` inteiro, com um monte de provas
    encadeadas, não consegue).
  * PROCESSO — `orq doctor` como subprocesso, provando a orquestração:
    prova fatal derruba o pré-voo, prova não-fatal só avisa, e a saída
    inteira sem nenhuma prova de mentira.

Nenhum teste aqui fala com o GitHub/Telegram/Claude reais — `gh`/
`orq-avisar` são os de mentira em testes/fixtures/bin/, escolhidos por PATH/
ORQ_NOTIFY_CMD. `claude`, `tmux`, `git`, `testes/cerca.sh` são os de VERDADE
desta máquina: são exatamente o que o spec pede provar por chamada real, e
esta suíte roda numa máquina que já tem os três.
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
FAKE_BIN = RAIZ / "testes" / "fixtures" / "bin"

os.environ.setdefault("ORQ_NOTIFY_CMD", str(FAKE_BIN / "orq-avisar"))
os.environ.setdefault("ORQ_CLICKUP_CMD", str(FAKE_BIN / "orq-clickup"))

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


class ComEsteiraDeMentira(unittest.TestCase):
    """Um banco com config completa e um repositório git de verdade —
    a base para a maioria das provas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.worktrees = self.raiz / "worktrees"
        self.worktrees.mkdir()
        self.caminho = self.raiz / "e.db"
        con = orq.criar_banco(self.caminho)
        for chave, valor in {
            "name": "esteira", "repo": str(self.repo.resolve()), "base_branch": "main",
            "worktree_root": str(self.worktrees), "github_repo": "acme/x",
        }.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()


# ==================================================================== MÓDULO

class ProvaBancoDestaMaquina(ComEsteiraDeMentira):
    def test_repo_desta_maquina_passa(self):
        antigo = Path.cwd()
        try:
            os.chdir(self.repo)
            con = orq.abrir_banco(self.caminho)
            ok, ev = orq._prova_banco_desta_maquina(con)
            con.close()
        finally:
            os.chdir(antigo)
        self.assertTrue(ok, ev)
        self.assertIn("esquema v", ev)

    def test_repo_de_outra_maquina_nao_da_verde(self):
        # O banco declara um `repo` que não é o repositório onde estamos
        # agora — o critério de aceite nomeado do spec.
        outro = self.raiz / "outro-repo-que-nao-existe-aqui"
        with orq.transacao(self.caminho) as con:
            orq.definir_config(con, "repo", str(outro))
        antigo = Path.cwd()
        try:
            os.chdir(self.repo)   # estamos no repo ORIGINAL, não no declarado
            con = orq.abrir_banco(self.caminho)
            ok, ev = orq._prova_banco_desta_maquina(con)
            con.close()
        finally:
            os.chdir(antigo)
        self.assertFalse(ok)
        self.assertIn(str(outro), ev)

    def test_sem_repo_declarado_falha(self):
        con = orq.criar_banco(self.raiz / "vazio.db")
        ok, ev = orq._prova_banco_desta_maquina(con)
        con.close()
        self.assertFalse(ok)
        self.assertIn("repo", ev)


class ProvaWalEDiscoLocal(ComEsteiraDeMentira):
    def test_wal_e_disco_local_de_verdade_passa(self):
        con = orq.abrir_banco(self.caminho)
        ok, ev = orq._prova_wal_e_disco_local(con, self.caminho)
        con.close()
        self.assertTrue(ok, ev)
        self.assertIn("wal", ev)

    def test_journal_mode_errado_falha(self):
        con = orq.abrir_banco(self.caminho)
        con.execute("PRAGMA journal_mode = DELETE")
        ok, ev = orq._prova_wal_e_disco_local(con, self.caminho)
        con.close()
        self.assertFalse(ok)

    def test_sistema_de_arquivos_de_rede_falha(self):
        con = orq.abrir_banco(self.caminho)
        with unittest.mock.patch.object(orq, "_tipo_sistema_arquivos", return_value="nfs"):
            ok, ev = orq._prova_wal_e_disco_local(con, self.caminho)
        con.close()
        self.assertFalse(ok)
        self.assertIn("rede", ev)


class ProvaFila(ComEsteiraDeMentira):
    def test_dois_escritores_concorrentes_nenhum_perde_e_limpa_depois(self):
        ok, ev = orq._prova_fila(self.caminho)
        self.assertTrue(ok, ev)
        self.assertIn("nenhum perdido", ev)
        con = orq.abrir_banco(self.caminho)
        sobrou = con.execute(
            "SELECT 1 FROM unidade WHERE chave = '__doctor__'").fetchone()
        con.close()
        self.assertIsNone(sobrou)   # a unidade reservada não fica para trás

    def test_limpa_mesmo_quando_um_escritor_falha(self):
        # Simula um escritor que levanta — a limpeza (finally) ainda roda.
        chamadas = {"n": 0}
        original = orq.transacao

        def as_vezes_quebra(caminho):
            chamadas["n"] += 1
            if chamadas["n"] == 3:   # a segunda ESCRITA concorrente (a 1ª é a criação)
                raise RuntimeError("falha simulada")
            return original(caminho)

        with unittest.mock.patch.object(orq, "transacao", side_effect=as_vezes_quebra):
            try:
                orq._prova_fila(self.caminho)
            except Exception:
                pass
        con = orq.abrir_banco(self.caminho)
        sobrou = con.execute(
            "SELECT 1 FROM unidade WHERE chave = '__doctor__'").fetchone()
        con.close()
        self.assertIsNone(sobrou)


class ProvaValidate(ComEsteiraDeMentira):
    def test_esteira_coerente_passa(self):
        con = orq.criar_banco(self.raiz / "outra.db")
        for chave, valor in {"repo": str(self.repo.resolve()), "base_branch": "main",
                             "worktree_root": str(self.worktrees), "github_repo": "acme/x"}.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        con.commit()
        ok, ev = orq._prova_validate(self.raiz / "outra.db")
        con.close()
        self.assertTrue(ok, ev)

    def test_esteira_incoerente_falha_com_o_motivo(self):
        con = orq.criar_banco(self.raiz / "quebrada.db")
        con.commit()
        con.close()
        ok, ev = orq._prova_validate(self.raiz / "quebrada.db")
        self.assertFalse(ok)
        self.assertIn("repo", ev)


class ProvaAgente(unittest.TestCase):
    def test_falta_de_processo_nao_vira_sem_login(self):
        # aprendizado nº 23: fork falhando não pode virar "sem login".
        def fake_run(args, *a, **kw):
            if args == ["true"]:
                raise OSError("EAGAIN: resource temporarily unavailable")
            raise AssertionError("não deveria chegar a chamar claude")

        with unittest.mock.patch.object(orq.subprocess, "run", side_effect=fake_run):
            ok, ev = orq._prova_agente()
        self.assertFalse(ok)
        self.assertIn("criar processo", ev)
        # a mensagem PODE mencionar "login" para dizer que NÃO é o caso — o
        # que não pode acontecer é recomendar `claude auth login`, a
        # instrução do OUTRO diagnóstico (credencial de verdade expirada).
        self.assertNotIn("auth login", ev)

    def test_claude_ausente_da_path_falha_claramente(self):
        with unittest.mock.patch.object(orq.shutil, "which", return_value=None):
            ok, ev = orq._prova_agente()
        self.assertFalse(ok)
        self.assertIn("PATH", ev)

    def test_claude_responde_ok_passa(self):
        def fake_run(args, *a, **kw):
            if args == ["true"]:
                return subprocess.CompletedProcess(args, 0)
            self.assertEqual(args[:2], ["claude", "-p"])
            return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

        with unittest.mock.patch.object(orq.shutil, "which", return_value="/usr/bin/claude"), \
             unittest.mock.patch.object(orq.subprocess, "run", side_effect=fake_run):
            ok, ev = orq._prova_agente()
        self.assertTrue(ok, ev)

    def test_claude_responde_algo_que_nao_e_ok_falha(self):
        def fake_run(args, *a, **kw):
            if args == ["true"]:
                return subprocess.CompletedProcess(args, 0)
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="401 unauthorized")

        with unittest.mock.patch.object(orq.shutil, "which", return_value="/usr/bin/claude"), \
             unittest.mock.patch.object(orq.subprocess, "run", side_effect=fake_run):
            ok, ev = orq._prova_agente()
        self.assertFalse(ok)
        self.assertIn("auth login", ev)


class ProvaGh(unittest.TestCase):
    def setUp(self):
        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_BIN}:{self._path_original}"
        for k in ("FAKE_GH_AUTH_OK", "FAKE_GH_PR_LIST_OK"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ["PATH"] = self._path_original
        for k in ("FAKE_GH_AUTH_OK", "FAKE_GH_PR_LIST_OK"):
            os.environ.pop(k, None)

    def test_autenticado_e_repo_acessivel_passa(self):
        ok, ev = orq._prova_gh("acme/x")
        self.assertTrue(ok, ev)

    def test_sem_autenticacao_e_fatal(self):
        os.environ["FAKE_GH_AUTH_OK"] = "0"
        ok, ev = orq._prova_gh("acme/x")
        self.assertFalse(ok)
        self.assertIn("gh auth login", ev)

    def test_repo_inacessivel_falha(self):
        os.environ["FAKE_GH_PR_LIST_OK"] = "0"
        ok, ev = orq._prova_gh("acme/x")
        self.assertFalse(ok)

    def test_sem_github_repo_declarado_so_confere_autenticacao(self):
        ok, ev = orq._prova_gh(None)
        self.assertTrue(ok, ev)
        self.assertIn("pulei", ev)


class ProvaGitCredencial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.origem = _novo_repo(self.raiz)   # faz as vezes de "origin", local

    def tearDown(self):
        self.tmp.cleanup()

    def test_remoto_local_alcancavel_passa(self):
        clone = self.raiz / "clone"
        _git(self.raiz, "clone", "-q", str(self.origem), str(clone))
        ok, ev = orq._prova_git_credencial(str(clone), "main")
        self.assertTrue(ok, ev)

    def test_sem_remoto_nenhum_falha(self):
        ok, ev = orq._prova_git_credencial(str(self.origem), "main")
        self.assertFalse(ok)
        self.assertIn("credencial", ev)


class ProvaTmux(unittest.TestCase):
    def test_tmux_de_verdade_desta_maquina_passa_ou_diz_por_que_nao(self):
        ok, ev = orq._prova_tmux()
        if orq.has_tmux():
            self.assertTrue(ok, ev)
        else:
            self.assertFalse(ok)

    def test_versao_abaixo_de_3_2_falha(self):
        with unittest.mock.patch.object(orq, "has_tmux", return_value=True), \
             unittest.mock.patch.object(
                 orq.subprocess, "run",
                 return_value=subprocess.CompletedProcess([], 0, stdout="tmux 3.1a\n")):
            ok, ev = orq._prova_tmux()
        self.assertFalse(ok)


class ProvaCerca(unittest.TestCase):
    def test_cerca_de_verdade_deste_repositorio_passa(self):
        ok, ev = orq._prova_cerca()
        self.assertTrue(ok, ev)
        self.assertIn("impressão", ev)
        self.assertIn("verde", ev)

    def test_impressao_e_um_sha_curto_e_estavel(self):
        a = orq.cerca_impressao()
        b = orq.cerca_impressao()
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_cerca_ausente_falha(self):
        with unittest.mock.patch.object(orq, "CERCA", Path("/nao/existe/cerca.sh")):
            ok, ev = orq._prova_cerca()
        self.assertFalse(ok)


class ProvaConfianca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self._claude_json_original = orq.CLAUDE_JSON
        orq.CLAUDE_JSON = self.raiz / "claude.json"

    def tearDown(self):
        orq.CLAUDE_JSON = self._claude_json_original
        self.tmp.cleanup()

    def test_repo_confiavel_passa(self):
        repo = str(self.raiz / "repo")
        orq.CLAUDE_JSON.write_text(json.dumps(
            {"projects": {str(Path(repo).expanduser()): {"hasTrustDialogAccepted": True}}}))
        ok, ev = orq._prova_confianca(repo)
        self.assertTrue(ok, ev)

    def test_repo_nao_confiavel_falha(self):
        orq.CLAUDE_JSON.write_text(json.dumps({"projects": {}}))
        ok, ev = orq._prova_confianca(str(self.raiz / "repo"))
        self.assertFalse(ok)

    def test_arquivo_ilegivel_falha(self):
        ok, ev = orq._prova_confianca(str(self.raiz / "repo"))   # claude.json nem existe
        self.assertFalse(ok)


class ProvaWorktreeFora(unittest.TestCase):
    def test_fora_do_repo_passa(self):
        ok, ev = orq._prova_worktree_fora("/tmp/repo", "/tmp/worktrees")
        self.assertTrue(ok, ev)

    def test_dentro_do_repo_falha(self):
        ok, ev = orq._prova_worktree_fora("/tmp/repo", "/tmp/repo/worktrees")
        self.assertFalse(ok)
        self.assertIn("DENTRO", ev)


class ProvaTelegram(unittest.TestCase):
    def setUp(self):
        self._notify_cmd_original = os.environ.get("ORQ_NOTIFY_CMD")
        os.environ["ORQ_NOTIFY_CMD"] = str(FAKE_BIN / "orq-avisar")
        os.environ.pop("FAKE_AVISAR_TESTAR", None)

    def tearDown(self):
        if self._notify_cmd_original is None:
            os.environ.pop("ORQ_NOTIFY_CMD", None)
        else:
            os.environ["ORQ_NOTIFY_CMD"] = self._notify_cmd_original
        os.environ.pop("FAKE_AVISAR_TESTAR", None)

    def test_credencial_configurada_entrega(self):
        os.environ["FAKE_AVISAR_TESTAR"] = "ok"
        ok, ev = orq._prova_telegram()
        self.assertTrue(ok, ev)
        self.assertIn("ok:", ev)

    def test_sem_credencial_avisa_sem_matar_o_chamador(self):
        ok, ev = orq._prova_telegram()
        self.assertFalse(ok)   # quem chama decide se isso é fatal — aqui não é


class ProvaCapacidade(ComEsteiraDeMentira):
    def test_devolve_bool_e_evidencia_com_numeros(self):
        con = orq.abrir_banco(self.caminho)
        ok, ev = orq._prova_capacidade(con)
        con.close()
        self.assertIsInstance(ok, bool)
        self.assertIn("RAM livre", ev)
        self.assertIn("vagas", ev)


class ContagemDeProcessos(unittest.TestCase):
    def test_nao_quebra_e_devolve_numeros(self):
        n, limite = orq._contagem_e_limite_de_processos()
        self.assertIsInstance(n, int)
        self.assertGreater(n, 0)   # ao menos este processo de teste existe


# =================================================================== PROCESSO

def orq_cli(db, *args, cwd=None, checar=False, env_extra=None):
    env = {**os.environ, "PATH": f"{FAKE_BIN}:{os.environ.get('PATH', '')}",
          "ORQ_NOTIFY_CMD": str(FAKE_BIN / "orq-avisar"),
          "FAKE_GH_AUTH_OK": "1", "FAKE_GH_PR_LIST_OK": "1",
          **(env_extra or {})}
    r = subprocess.run(
        [sys.executable, str(ORQ_BIN), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=60, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class DoctorComoSubprocesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.repo = _novo_repo(self.raiz)
        self.worktrees = self.raiz / "worktrees"
        self.worktrees.mkdir()
        self.db = self.raiz / "e.db"
        con = orq.criar_banco(self.db)
        for chave, valor in {
            "name": "esteira", "repo": str(self.repo.resolve()), "base_branch": "main",
            "worktree_root": str(self.worktrees), "github_repo": "acme/x",
        }.items():
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_gh_desautenticado_e_fatal(self):
        r = orq_cli(self.db, "doctor", "--rapido", cwd=str(self.repo),
                   env_extra={"FAKE_GH_AUTH_OK": "0"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gh auth login", r.stdout)

    def test_telegram_ausente_avisa_mas_nao_mata_o_resto(self):
        r = orq_cli(self.db, "doctor", "--rapido", cwd=str(self.repo))
        self.assertIn("telegram entrega", r.stdout)
        # a linha do telegram usa "!" (aviso), nunca "✗" (fatal)
        linha_telegram = next(l for l in r.stdout.splitlines() if "telegram entrega" in l)
        self.assertIn("!", linha_telegram)
        self.assertNotIn("✗", linha_telegram)

    def test_roda_sem_credenciais_de_clickup_nenhures(self):
        # Nenhuma prova deste comando toca ClickUp — nem token, nem lista.
        r = orq_cli(self.db, "doctor", "--rapido", cwd=str(self.repo),
                   env_extra={"ORQ_CREDENCIAIS": str(self.raiz / "nao-existe.env")})
        self.assertNotIn("clickup", r.stdout.lower())

    def test_rapido_avisa_que_pulou_sem_fingir_verde_de_verdade(self):
        r = orq_cli(self.db, "doctor", "--rapido", cwd=str(self.repo))
        self.assertIn("pulado por --rapido", r.stdout)
        self.assertIn("NÃO é prova", r.stdout)

    def test_nenhuma_prova_imprime_so_a_palavra_ok(self):
        r = orq_cli(self.db, "doctor", "--rapido", cwd=str(self.repo))
        for linha in r.stdout.splitlines():
            if linha.strip().startswith(("✓", "✗", "!")):
                # cada linha carrega evidência depois do rótulo — não é só o símbolo
                self.assertGreater(len(linha.strip()), 40, linha)


if __name__ == "__main__":
    unittest.main()
