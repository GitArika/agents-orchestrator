"""Testes dos verbos de declaração (OA-02): orq init/task/dep/config/export/validate.

Diferente de test_estado.py (funções puras, carregadas em processo), aqui o
alvo é o próprio CLI — `main()` e a montagem do argparse. Roda `bin/orq` como
subprocesso contra um repositório git de mentira, porque é isso que prova que
os comandos estão de fato REGISTRADOS e ligados aos verbos certos, não só que
as funções por baixo funcionam.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORQ = RAIZ / "bin" / "orq"


def orq(db, *args, cwd=None, checar=True):
    r = subprocess.run(
        [sys.executable, str(ORQ), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30)
    if checar and r.returncode != 0:
        raise AssertionError(
            f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class ComRepoDeMentira(unittest.TestCase):
    """Repositório git real, com CLAUDE.md, e um banco novo — o par que os
    verbos de declaração pressupõem."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.repo = raiz / "repo"
        self.worktrees = raiz / "worktrees"
        self.db = raiz / "esteira.db"
        self.repo.mkdir()
        self.worktrees.mkdir()
        for cmd in (["git", "init", "-q"],
                    ["git", "config", "user.email", "t@t.com"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)
        (self.repo / "CLAUDE.md").write_text("# regras do projeto\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=self.repo,
                       check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _init(self, **extra):
        args = ["init", "--nome", "smoke", "--repo", str(self.repo), "--base", "main",
                "--worktrees", str(self.worktrees), "--github", "acme/smoke"]
        for k, v in extra.items():
            args += [f"--{k}", v]
        return orq(self.db, *args)


class Init(ComRepoDeMentira):
    def test_cria_o_banco_e_a_config(self):
        self._init()
        self.assertTrue(self.db.exists())
        r = orq(self.db, "config", "list")
        # `cmd_init` resolve o caminho (segue symlink) antes de gravar — no
        # macOS /tmp é symlink para /private/tmp, então comparamos resolvido.
        self.assertIn(f"repo = {self.repo.resolve()}", r.stdout)
        self.assertIn("base_branch = main", r.stdout)
        self.assertIn("github_repo = acme/smoke", r.stdout)

    def test_recusa_sobrescrever_sem_forcar(self):
        self._init()
        r = orq(self.db, "init", "--nome", "smoke", "--repo", str(self.repo),
               "--base", "main", "--worktrees", str(self.worktrees), checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_recusa_worktrees_dentro_do_repo(self):
        dentro = self.repo / "worktrees-internas"
        r = orq(self.db, "init", "--nome", "smoke", "--repo", str(self.repo),
               "--base", "main", "--worktrees", str(dentro), checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DENTRO", r.stdout + r.stderr)

    def test_recusa_branch_base_inexistente(self):
        r = orq(self.db, "init", "--nome", "smoke", "--repo", str(self.repo),
               "--base", "nao-existe", "--worktrees", str(self.worktrees), checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_recusa_sem_flag_db(self):
        r = subprocess.run(
            [sys.executable, str(ORQ), "init", "--nome", "x", "--repo", str(self.repo),
             "--base", "main", "--worktrees", str(self.worktrees)],
            capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--db", r.stdout + r.stderr)


class Task(ComRepoDeMentira):
    def setUp(self):
        super().setUp()
        self._init()

    def test_declara_uma_unidade(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "868001",
           "--titulo", "Primeira unidade")
        r = orq(self.db, "export", "--formato", "json")
        dados = json.loads(r.stdout)
        self.assertEqual(len(dados["unidades"]), 1)
        self.assertEqual(dados["unidades"][0]["chave"], "FE-01")

    def test_repetir_com_mesmos_valores_e_idempotente(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "868001", "--titulo", "t")
        r = orq(self.db, "task", "add", "FE-01", "--clickup", "868001", "--titulo", "t")
        self.assertIn("sem mudança", r.stdout)
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        self.assertEqual(len(dados["unidades"]), 1)

    def test_repetir_com_valores_diferentes_exige_forcar(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "868001", "--titulo", "t")
        r = orq(self.db, "task", "add", "FE-01", "--clickup", "868001",
               "--titulo", "outro título", checar=False)
        self.assertNotEqual(r.returncode, 0)
        r = orq(self.db, "task", "add", "FE-01", "--clickup", "868001",
               "--titulo", "outro título", "--forcar")
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        self.assertEqual(dados["unidades"][0]["titulo"], "outro título")

    def test_prioridade_desconhecida_recusa(self):
        r = orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "t",
               "--prioridade", "inventada", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_set_altera_so_o_que_foi_passado(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "t")
        orq(self.db, "task", "set", "FE-01", "--prioridade", "alta")
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        u = dados["unidades"][0]
        self.assertEqual(u["titulo"], "t")          # não mudou
        self.assertEqual(u["prioridade"], 1)          # alta = 1

    def test_rm_exige_forcar(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "t")
        r = orq(self.db, "task", "rm", "FE-01", checar=False)
        self.assertNotEqual(r.returncode, 0)
        orq(self.db, "task", "rm", "FE-01", "--forcar")
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        self.assertEqual(dados["unidades"], [])

    def test_rm_recusa_unidade_em_progresso_mesmo_com_forcar(self):
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "t")
        subprocess.run(
            [sys.executable, "-c",
             f"import sqlite3; c=sqlite3.connect(r'{self.db}'); "
             f"c.execute(\"UPDATE unidade SET status='em_progresso' WHERE chave='FE-01'\"); "
             f"c.commit()"],
            check=True)
        r = orq(self.db, "task", "rm", "FE-01", "--forcar", checar=False)
        self.assertNotEqual(r.returncode, 0)


class Dep(ComRepoDeMentira):
    def setUp(self):
        super().setUp()
        self._init()
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "a")
        orq(self.db, "task", "add", "FE-02", "--clickup", "2", "--titulo", "b")
        orq(self.db, "task", "add", "FE-03", "--clickup", "3", "--titulo", "c")

    def test_declara_dependencia(self):
        orq(self.db, "dep", "add", "FE-03", "--precisa", "FE-01", "--precisa", "FE-02")
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        u3 = next(u for u in dados["unidades"] if u["chave"] == "FE-03")
        self.assertEqual(sorted(u3["depends_on"]), ["FE-01", "FE-02"])

    def test_ciclo_recusa_com_caminho_fechado(self):
        orq(self.db, "dep", "add", "FE-02", "--precisa", "FE-01")
        r = orq(self.db, "dep", "add", "FE-01", "--precisa", "FE-02", checar=False)
        self.assertNotEqual(r.returncode, 0)
        saida = r.stdout + r.stderr
        self.assertIn("FE-02 → FE-01 → FE-02", saida)

    def test_dependencia_de_unidade_inexistente_recusa(self):
        r = orq(self.db, "dep", "add", "FE-01", "--precisa", "FANTASMA", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_rm_remove(self):
        orq(self.db, "dep", "add", "FE-03", "--precisa", "FE-01")
        orq(self.db, "dep", "rm", "FE-03", "--precisa", "FE-01")
        dados = json.loads(orq(self.db, "export", "--formato", "json").stdout)
        u3 = next(u for u in dados["unidades"] if u["chave"] == "FE-03")
        self.assertEqual(u3["depends_on"], [])


class Config(ComRepoDeMentira):
    def setUp(self):
        super().setUp()
        self._init()

    def test_set_get(self):
        orq(self.db, "config", "set", "max_concurrent", "6")
        r = orq(self.db, "config", "get", "max_concurrent")
        self.assertEqual(r.stdout.strip(), "6")

    def test_chave_desconhecida_recusa(self):
        r = orq(self.db, "config", "set", "chave_inventada", "1", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_get_de_chave_ausente_recusa(self):
        r = orq(self.db, "config", "get", "model", checar=False)
        self.assertNotEqual(r.returncode, 0)


class Export(ComRepoDeMentira):
    def setUp(self):
        super().setUp()
        self._init()
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "a")
        orq(self.db, "task", "add", "FE-02", "--clickup", "2", "--titulo", "b")
        orq(self.db, "dep", "add", "FE-02", "--precisa", "FE-01")

    def test_export_e_estavel(self):
        a = orq(self.db, "export").stdout
        b = orq(self.db, "export").stdout
        self.assertEqual(a, b)

    def test_export_json_e_estavel_e_valido(self):
        a = orq(self.db, "export", "--formato", "json").stdout
        b = orq(self.db, "export", "--formato", "json").stdout
        self.assertEqual(a, b)
        json.loads(a)   # não levanta

    def test_export_toml_tem_as_duas_unidades(self):
        saida = orq(self.db, "export").stdout
        self.assertEqual(saida.count("[[unidade]]"), 2)
        self.assertIn('depends_on = ["FE-01"]', saida)


class Validate(ComRepoDeMentira):
    def test_esteira_completa_passa(self):
        self._init()
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "a")
        r = orq(self.db, "validate")
        self.assertEqual(r.returncode, 0)

    def test_sem_github_repo_recusa(self):
        orq(self.db, "init", "--nome", "smoke", "--repo", str(self.repo),
           "--base", "main", "--worktrees", str(self.worktrees))   # sem --github
        orq(self.db, "task", "add", "FE-01", "--clickup", "1", "--titulo", "a")
        r = orq(self.db, "validate", checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("github_repo", r.stdout)

    def test_sem_claude_md_nem_agents_md_recusa(self):
        (self.repo / "CLAUDE.md").unlink()
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "remove CLAUDE.md"], cwd=self.repo,
                       check=True, capture_output=True)
        self._init()
        r = orq(self.db, "validate", checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CLAUDE.md", r.stdout)

    def test_unidade_sem_titulo_ou_clickup_recusa(self):
        self._init()
        # criado direto no banco para simular um banco editado por fora dos verbos
        subprocess.run(
            [sys.executable, "-c",
             f"import sqlite3,time; c=sqlite3.connect(r'{self.db}'); "
             f"c.execute(\"INSERT INTO unidade (chave,titulo,criado_em,atualizado_em) "
             f"VALUES ('FE-99','',datetime('now'),datetime('now'))\"); c.commit()"],
            check=True)
        r = orq(self.db, "validate", checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FE-99", r.stdout)

    def test_max_concurrent_invalido_recusa(self):
        self._init()
        orq(self.db, "config", "set", "max_concurrent", "0")
        r = orq(self.db, "validate", checar=False)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
