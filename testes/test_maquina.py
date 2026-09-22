"""Testes da máquina de cinco estados (OA-03).

Duas camadas, como o resto da suíte:
  * MÓDULO — bin/orq carregado via SourceFileLoader (mesmo padrão de
    test_estado.py), testando `transicionar`, `sessao_viva`,
    `recolher_sessoes_mortas`, `unidades_prontas`, `classificar` e
    `resolver_banco` diretamente — inclusive o ciclo de vida inteiro
    (backlog → em_progresso → revisão → pronto libera dependente), montado
    com as funções de biblioteca (não `orq run`, que é CLI e tem suíte
    própria: testes/test_lancador.py, OA-05).
  * PROCESSO — bin/orq como subprocesso com --db explícito (mesmo padrão de
    test_verbos.py), provando que board/next/status/show/hold/release/
    reopen/advance/tick estão de fato religados.

`advance` faz uma chamada de rede real (`gh pr view`, OA-05) — por isso todo
teste de processo aqui roda com um `gh` de mentira na PATH
(testes/fixtures/bin/gh) que nunca fala com o GitHub de verdade.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORQ_BIN = RAIZ / "bin" / "orq"

# `orq-avisar` de mentira (OA-11): nenhum teste deste arquivo entrega aviso
# de verdade, mesmo que a máquina tenha credenciais reais configuradas —
# hold/advance/tick geram eventos roteados (bloqueada, pr_aberto, pr_fundido).
os.environ.setdefault("ORQ_NOTIFY_CMD", str(RAIZ / "testes" / "fixtures" / "bin" / "orq-avisar"))

_loader = importlib.machinery.SourceFileLoader("orq", str(ORQ_BIN))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


# ==================================================================== MÓDULO

class BancoComDuasUnidades(unittest.TestCase):
    """FE-01 e FE-02, sem dependência entre si — base para a maioria dos
    testes de módulo desta unidade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-01", clickup_id="1", titulo="a")
        self.b = orq.criar_unidade(con, "FE-02", clickup_id="2", titulo="b")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()


class TransicoesLegais(BancoComDuasUnidades):
    def test_todas_as_nove_transicoes_da_tabela_passam(self):
        casos = [
            ("backlog", "em_progresso"),
            ("em_progresso", "revisao"),
            ("em_progresso", "bloqueado"),
            ("em_progresso", "backlog"),
            ("revisao", "pronto"),
            ("revisao", "em_progresso"),
            ("revisao", "bloqueado"),
            ("bloqueado", "backlog"),
        ]
        with orq.transacao(self.caminho) as con:
            for de, para in casos:
                con.execute("UPDATE unidade SET status = ? WHERE id = ?", (de, self.a))
                orq.transicionar(con, self.a, para)
                atual = con.execute(
                    "SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
                self.assertEqual(atual, para, f"{de} -> {para}")

    def test_transicao_fora_da_tabela_e_recusada_nomeando_a_transicao(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")   # backlog->em_progresso: legal
        with self.assertRaises(orq.ErroTransicaoIlegal) as ctx:
            with orq.transacao(self.caminho) as con:
                orq.transicionar(con, self.a, "pronto")   # em_progresso->pronto: não existe
        self.assertIn("em_progresso", str(ctx.exception))
        self.assertIn("pronto", str(ctx.exception))

    def test_pronto_e_terminal_sem_forcar(self):
        with orq.transacao(self.caminho) as con:
            con.execute("UPDATE unidade SET status = 'pronto' WHERE id = ?", (self.a,))
        with self.assertRaises(orq.ErroTransicaoIlegal):
            with orq.transacao(self.caminho) as con:
                orq.transicionar(con, self.a, "em_progresso")

    def test_forcar_permite_transicao_fora_da_tabela(self):
        with orq.transacao(self.caminho) as con:
            con.execute("UPDATE unidade SET status = 'pronto' WHERE id = ?", (self.a,))
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "backlog", forcar=True)
        con = orq.abrir_banco(self.caminho)
        status = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        con.close()
        self.assertEqual(status, "backlog")

    def test_transicao_ilegal_nao_grava_nada(self):
        with self.assertRaises(orq.ErroTransicaoIlegal):
            with orq.transacao(self.caminho) as con:
                orq.transicionar(con, self.a, "pronto")   # backlog->pronto não existe
        con = orq.abrir_banco(self.caminho)
        status = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        n = con.execute("SELECT count(*) FROM evento WHERE tipo = 'transicao'").fetchone()[0]
        con.close()
        self.assertEqual(status, "backlog")
        self.assertEqual(n, 0)

    def test_status_desconhecido_recusa(self):
        with self.assertRaises(orq.ErroEstado):
            with orq.transacao(self.caminho) as con:
                orq.transicionar(con, self.a, "cancelado", forcar=True)


class SessaoViva(BancoComDuasUnidades):
    def test_sem_sessao_registrada_e_falso(self):
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq.sessao_viva(con, self.a))
        con.close()

    def test_pid_do_proprio_processo_e_vivo(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_sessao(con, self.a, worktree="/tmp/wt", branch="b",
                                 pid=os.getpid())
        con = orq.abrir_banco(self.caminho)
        self.assertTrue(orq.sessao_viva(con, self.a))
        con.close()

    def test_pid_inexistente_e_morto(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_sessao(con, self.a, worktree="/tmp/wt", branch="b", pid=999999999)
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq.sessao_viva(con, self.a))
        con.close()

    def test_encerrar_torna_a_sessao_morta(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_sessao(con, self.a, worktree="/tmp/wt", branch="b", pid=os.getpid())
            orq.encerrar_sessao(con, self.a, "teste")
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq.sessao_viva(con, self.a))
        con.close()

    @unittest.skipUnless(orq.has_tmux(), "tmux ausente")
    def test_tmux_de_verdade(self):
        nome = f"orq-teste-{os.getpid()}"
        subprocess.run(["tmux", "new-session", "-d", "-s", nome, "sleep", "60"], check=True)
        try:
            with orq.transacao(self.caminho) as con:
                orq.registrar_sessao(con, self.a, worktree="/tmp/wt", branch="b", tmux=nome)
            con = orq.abrir_banco(self.caminho)
            self.assertTrue(orq.sessao_viva(con, self.a))
            con.close()
        finally:
            subprocess.run(["tmux", "kill-session", "-t", nome], capture_output=True)
        con = orq.abrir_banco(self.caminho)
        self.assertFalse(orq.sessao_viva(con, self.a))
        con.close()


class RecolherSessoesMortas(BancoComDuasUnidades):
    def test_sem_sessao_recolhe_com_strike_1(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)
        self.assertEqual(len(recolhidas), 1)
        self.assertEqual(recolhidas[0]["desfecho"], "recolhida")
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT status, strikes FROM unidade WHERE id = ?", (self.a,)).fetchone()
        n_eventos = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'recolhida'",
            (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["strikes"], 1)
        self.assertEqual(n_eventos, 1)

    def test_atinge_max_strikes_vira_bloqueado(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
        with orq.transacao(self.caminho) as con:
            orq.recolher_sessoes_mortas(con, max_strikes=2)   # strike 1 -> backlog
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")      # redespachada
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)   # strike 2 -> bloqueado
        self.assertEqual(recolhidas[0]["desfecho"], "quarentena")
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT status, motivo, strikes FROM unidade WHERE id = ?",
                        (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "bloqueado")
        self.assertIn("2", u["motivo"])
        self.assertEqual(u["strikes"], 2)

    def test_sessao_viva_nao_e_recolhida(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.registrar_sessao(con, self.a, worktree="/tmp/wt", branch="b", pid=os.getpid())
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)
        self.assertEqual(recolhidas, [])
        con = orq.abrir_banco(self.caminho)
        status = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        con.close()
        self.assertEqual(status, "em_progresso")

    def test_unidade_fora_de_em_progresso_e_ignorada(self):
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)
        self.assertEqual(recolhidas, [])

    def test_solta_em_perdoa_a_primeira_falta_e_e_consumido(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            con.execute("UPDATE unidade SET solta_em = ? WHERE id = ?",
                       (orq._agora(), self.a))
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)
        self.assertEqual(recolhidas[0]["desfecho"], "liberada")
        con = orq.abrir_banco(self.caminho)
        u = con.execute("SELECT status, strikes, solta_em FROM unidade WHERE id = ?",
                        (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["strikes"], 0)             # não conta falta
        self.assertIsNone(u["solta_em"])               # bilhete consumido

        # a SEGUNDA vez (bilhete já gasto) volta a contar falta normalmente.
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
        with orq.transacao(self.caminho) as con:
            recolhidas = orq.recolher_sessoes_mortas(con, max_strikes=2)
        self.assertEqual(recolhidas[0]["desfecho"], "recolhida")
        con = orq.abrir_banco(self.caminho)
        strikes = con.execute("SELECT strikes FROM unidade WHERE id = ?", (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(strikes, 1)


class FilaDeDespacho(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a", prioridade=2)
        self.b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b", prioridade=2)
        self.c = orq.criar_unidade(con, "FE-C", clickup_id="3", titulo="c", prioridade=0)
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_dependencia_nao_pronta_nao_libera(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)   # B depende de A
        con = orq.abrir_banco(self.caminho)
        chaves = {r["chave"] for r in orq.unidades_prontas(con)}
        con.close()
        self.assertIn("FE-A", chaves)
        self.assertNotIn("FE-B", chaves)

    def test_dependencia_em_revisao_ainda_nao_libera(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)
            con.execute("UPDATE unidade SET status = 'revisao' WHERE id = ?", (self.a,))
        con = orq.abrir_banco(self.caminho)
        chaves = {r["chave"] for r in orq.unidades_prontas(con)}
        con.close()
        self.assertNotIn("FE-B", chaves)

    def test_dependencia_pronta_libera(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)
            con.execute("UPDATE unidade SET status = 'pronto' WHERE id = ?", (self.a,))
        con = orq.abrir_banco(self.caminho)
        chaves = {r["chave"] for r in orq.unidades_prontas(con)}
        con.close()
        self.assertIn("FE-B", chaves)

    def test_ordem_por_prioridade_depois_desbloqueio_depois_chave(self):
        with orq.transacao(self.caminho) as con:
            orq.adicionar_dependencia(con, self.b, self.a)   # A desbloqueia B
        con = orq.abrir_banco(self.caminho)
        ordem = [r["chave"] for r in orq.unidades_prontas(con)]
        con.close()
        # FE-C tem prioridade mais alta (0 = urgente) -> vem primeiro.
        # Entre FE-A e (o que sobrar) FE-A desbloqueia FE-B -> vem antes de
        # qualquer outra unidade de mesma prioridade que não desbloqueia nada.
        self.assertEqual(ordem[0], "FE-C")
        self.assertEqual(ordem[1], "FE-A")


class BacklogProntaVsTravada(unittest.TestCase):
    """O critério de aceite central: a distinção é CALCULADA, nunca gravada."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        self.b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        con.commit(); con.close()   # ANTES de abrir a segunda conexão — senão
                                    # a transação implícita ainda aberta em
                                    # `con` segura o lock de escrita e
                                    # `transacao()` trava em "database is locked"
        with orq.transacao(self.caminho) as c2:
            orq.adicionar_dependencia(c2, self.b, self.a)
            c2.execute("UPDATE unidade SET status = 'revisao' WHERE id = ?", (self.a,))

    def tearDown(self):
        self.tmp.cleanup()

    def test_travada_enquanto_dependencia_nao_e_pronto_e_pronta_depois_sem_escrita_no_meio(self):
        con = orq.abrir_banco(self.caminho)
        antes = {l["unidade"]["chave"]: l["estado"] for l in orq.classificar(con)}
        con.close()
        self.assertEqual(antes["FE-B"], "blocked")

        # a ÚNICA escrita é na dependência (A), não em B.
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "pronto")

        con = orq.abrir_banco(self.caminho)
        depois = {l["unidade"]["chave"]: l["estado"] for l in orq.classificar(con)}
        con.close()
        self.assertEqual(depois["FE-B"], "ready")
        # B nunca foi escrita: seu status cru continua 'backlog' o tempo todo.
        con = orq.abrir_banco(self.caminho)
        status_b = con.execute("SELECT status FROM unidade WHERE id = ?", (self.b,)).fetchone()["status"]
        con.close()
        self.assertEqual(status_b, "backlog")


class CicloDeVidaInteiro(unittest.TestCase):
    """backlog → em_progresso → revisão → pronto libera dependente. Via
    biblioteca (não CLI): `orq run`/`orq advance` como comando dependem do
    que só existe a partir de OA-05."""

    def test_ciclo_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "teste.db"
            con = orq.criar_banco(caminho)
            a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
            b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
            con.commit(); con.close()
            with orq.transacao(caminho) as c:
                orq.adicionar_dependencia(c, b, a)

            con = orq.abrir_banco(caminho)
            self.assertIn("FE-A", {r["chave"] for r in orq.unidades_prontas(con)})
            self.assertNotIn("FE-B", {r["chave"] for r in orq.unidades_prontas(con)})
            con.close()

            with orq.transacao(caminho) as c:
                orq.transicionar(c, a, "em_progresso")
            with orq.transacao(caminho) as c:
                orq.transicionar(c, a, "revisao")
            con = orq.abrir_banco(caminho)
            self.assertNotIn("FE-B", {r["chave"] for r in orq.unidades_prontas(con)})
            con.close()

            with orq.transacao(caminho) as c:
                orq.transicionar(c, a, "pronto")
            con = orq.abrir_banco(caminho)
            self.assertIn("FE-B", {r["chave"] for r in orq.unidades_prontas(con)})
            con.close()


class ResolverBanco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self._bancos_original = orq.BANCOS
        self._ultimo_original = orq.ULTIMO_BANCO
        orq.BANCOS = self.raiz / "esteiras"
        orq.BANCOS.mkdir()
        orq.ULTIMO_BANCO = self.raiz / "last-db"
        for var in ("ORQ_DB",):
            os.environ.pop(var, None)

    def tearDown(self):
        orq.BANCOS = self._bancos_original
        orq.ULTIMO_BANCO = self._ultimo_original
        os.environ.pop("ORQ_DB", None)
        self.tmp.cleanup()

    def test_explicito_sempre_vence(self):
        caminho = self.raiz / "x.db"
        orq.criar_banco(caminho).close()
        self.assertEqual(orq.resolver_banco(str(caminho)), caminho.resolve())

    def test_explicito_inexistente_recusa(self):
        with self.assertRaises(SystemExit):
            orq.resolver_banco(str(self.raiz / "nao-existe.db"))

    def test_env_var_e_usada_quando_nenhum_explicito(self):
        caminho = self.raiz / "y.db"
        orq.criar_banco(caminho).close()
        os.environ["ORQ_DB"] = str(caminho)
        self.assertEqual(orq.resolver_banco(None), caminho.resolve())

    def test_nenhum_candidato_recusa(self):
        with self.assertRaises(SystemExit):
            orq.resolver_banco(None)

    def test_ultimo_usado_como_ultimo_recurso(self):
        caminho = self.raiz / "z.db"
        orq.criar_banco(caminho).close()
        orq.ULTIMO_BANCO.write_text(str(caminho))
        self.assertEqual(orq.resolver_banco(None), caminho)

    def test_descoberta_por_repositorio_desta_maquina(self):
        repo = self.raiz / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        caminho = self.raiz / "esteiras" / "achavel.db"
        con = orq.criar_banco(caminho)
        # `cmd_init` grava `repo` RESOLVIDO (segue symlink) — replicamos aqui,
        # senão a comparação textual de `divergencia_de_maquina` nunca bate
        # com o git-common-dir (que também vem resolvido).
        con.execute("INSERT INTO config (chave, valor) VALUES ('repo', ?)",
                   (str(repo.resolve()),))
        con.commit(); con.close()
        antigo = Path.cwd()
        try:
            os.chdir(repo)
            self.assertEqual(orq.resolver_banco(None), caminho)
        finally:
            os.chdir(antigo)


# =================================================================== PROCESSO

FAKE_GH = RAIZ / "testes" / "fixtures" / "bin"


def orq_cli(db, *args, cwd=None, checar=True, env_extra=None):
    # `gh` de mentira na PATH (testes/fixtures/bin/gh): nenhum teste aqui
    # fala com a API real do GitHub. Por padrão diz que QUALQUER PR existe
    # (FAKE_GH_PRS_OK="*") — quem quiser testar a recusa passa
    # env_extra={"FAKE_GH_PRS_OK": "..."} ou "" (nenhum PR existe).
    env = {**os.environ, "PATH": f"{FAKE_GH}:{os.environ.get('PATH', '')}",
          "FAKE_GH_PRS_OK": "*", **(env_extra or {})}
    r = subprocess.run(
        [sys.executable, str(ORQ_BIN), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(
            f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def _direto(db, fn, *args, **kwargs):
    """Chama uma função de biblioteca numa transação própria — usado pelos
    testes de processo para montar cenários (sessão viva, status intermediário)
    que nenhum verbo de CLI cria sozinho ainda."""
    with orq.transacao(db) as con:
        return fn(con, *args, **kwargs)


class ComoSubprocesso(unittest.TestCase):
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

    def tearDown(self):
        self.tmp.cleanup()

    def test_board_mostra_pronta_e_travada(self):
        r = orq_cli(self.db, "board")
        self.assertIn("FE-A", r.stdout)
        self.assertIn("FE-B", r.stdout)
        self.assertIn("pronta para começar", r.stdout)
        self.assertIn("espera:", r.stdout)

    def test_next_lista_so_o_pronto(self):
        r = orq_cli(self.db, "next")
        self.assertIn("FE-A", r.stdout)
        self.assertNotIn("FE-B", r.stdout)

    def test_next_com_n_limita(self):
        _direto(self.db, orq.definir_status, self.b, "backlog")   # já é, no-op
        r = orq_cli(self.db, "next", "-n", "1")
        self.assertIn("FE-A", r.stdout)

    def test_advance_exige_pr(self):
        r = orq_cli(self.db, "advance", "FE-A", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_advance_de_backlog_e_ilegal(self):
        r = orq_cli(self.db, "advance", "FE-A", "--pr", "7", checar=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ilegal", r.stdout + r.stderr)

    def test_advance_de_em_progresso_grava_pr_e_vai_para_revisao(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        r = orq_cli(self.db, "advance", "FE-A", "--pr", "123")
        self.assertIn("123", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, pr_numero, pr_url FROM unidade WHERE id = ?",
                        (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "revisao")
        self.assertEqual(u["pr_numero"], 123)
        self.assertIn("acme/x", u["pr_url"])

    def test_advance_aceita_url_completa(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        orq_cli(self.db, "advance", "FE-A", "--pr", "https://github.com/acme/x/pull/55")
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT pr_numero, pr_url FROM unidade WHERE id = ?", (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["pr_numero"], 55)
        self.assertEqual(u["pr_url"], "https://github.com/acme/x/pull/55")

    def test_advance_nao_depende_de_ler_os_checks_de_ci(self):
        # Um token sem leitura de checks faz a visão padrão de `gh pr view`
        # falhar com o PR existindo — medido em 22/09/2026 no mine-one. A
        # checagem de existência não pode depender disso.
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        orq_cli(self.db, "advance", "FE-A", "--pr", "25", env_extra={"FAKE_GH_SEM_CHECKS": "1"})
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "revisao")

    def test_encerramento_espera_o_passo_8_so_de_dentro_da_sessao(self):
        # De dentro da sessão o briefing ainda manda espelhar o cartão; com
        # 3 s ela morria no meio disso (DS-05 do mine-one, 22/09/2026).
        antigo = os.environ.pop("ORQ_UNIT", None)
        try:
            self.assertEqual(orq._atraso_encerramento("FE-A"), 3)
            os.environ["ORQ_UNIT"] = "FE-A"
            self.assertEqual(orq._atraso_encerramento("FE-A"), orq.ESPERA_PASSO_8_S)
            self.assertEqual(orq._atraso_encerramento("FE-B"), 3)
        finally:
            os.environ.pop("ORQ_UNIT", None)
            if antigo is not None:
                os.environ["ORQ_UNIT"] = antigo

    def test_hold_exige_motivo_com_tamanho_minimo(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        r = orq_cli(self.db, "hold", "FE-A", "--motivo", "curto", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_hold_bloqueia_e_release_devolve_a_fila(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        orq_cli(self.db, "hold", "FE-A", "--motivo", "esperando decisão de produto")
        con = orq.abrir_banco(self.db)
        status = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        con.close()
        self.assertEqual(status, "bloqueado")

        orq_cli(self.db, "release", "FE-A")
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, strikes, solta_em FROM unidade WHERE id = ?",
                        (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["strikes"], 0)
        self.assertIsNotNone(u["solta_em"])

    def test_release_nao_gera_falta_no_tick_seguinte(self):
        """hold -> release -> tick: strikes continua 0."""
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        orq_cli(self.db, "hold", "FE-A", "--motivo", "esperando decisão de produto")
        orq_cli(self.db, "release", "FE-A")
        _direto(self.db, orq.transicionar, self.a, "em_progresso")   # redespachada
        orq_cli(self.db, "tick")
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, strikes FROM unidade WHERE id = ?", (self.a,)).fetchone()
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["strikes"], 0)   # perdoada, não falta

    def test_tick_recolhe_sessao_morta_com_strike(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        r = orq_cli(self.db, "tick")
        self.assertIn("FE-A", r.stdout)
        con = orq.abrir_banco(self.db)
        u = con.execute("SELECT status, strikes FROM unidade WHERE id = ?", (self.a,)).fetchone()
        n_eventos = con.execute(
            "SELECT count(*) FROM evento WHERE unidade_id = ? AND tipo = 'recolhida'",
            (self.a,)).fetchone()[0]
        con.close()
        self.assertEqual(u["status"], "backlog")
        self.assertEqual(u["strikes"], 1)
        self.assertEqual(n_eventos, 1)

    def test_reopen_sem_forcar_recusa(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        _direto(self.db, orq.transicionar, self.a, "revisao")
        _direto(self.db, orq.transicionar, self.a, "pronto")
        r = orq_cli(self.db, "reopen", "FE-A", checar=False)
        self.assertNotEqual(r.returncode, 0)

    def test_reopen_com_forcar_volta_para_backlog(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        _direto(self.db, orq.transicionar, self.a, "revisao")
        _direto(self.db, orq.transicionar, self.a, "pronto")
        orq_cli(self.db, "reopen", "FE-A", "--forcar")
        con = orq.abrir_banco(self.db)
        status = con.execute("SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        con.close()
        self.assertEqual(status, "backlog")

    def test_show_imprime_status_dependencias_e_eventos(self):
        r = orq_cli(self.db, "show", "FE-B")
        self.assertIn("depende de: FE-A", r.stdout)
        self.assertIn("status: backlog", r.stdout)

    def test_status_lista_vivas_e_esperando(self):
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        _direto(self.db, orq.registrar_sessao, self.a, worktree="/tmp/w", branch="b",
               pid=os.getpid())
        r = orq_cli(self.db, "status")
        self.assertIn("FE-A", r.stdout)

    def test_ciclo_completo_via_cli_com_ajuda_de_biblioteca(self):
        """backlog -> em_progresso -> revisão -> pronto (forçado, simulando o
        vigia de PR que só chega em OA-08) libera FE-B — provado pelo board."""
        _direto(self.db, orq.transicionar, self.a, "em_progresso")
        orq_cli(self.db, "advance", "FE-A", "--pr", "9")
        _direto(self.db, orq.transicionar, self.a, "pronto", tipo_evento="pr_fundido")
        r = orq_cli(self.db, "board")
        linhas = {l.split()[1]: l for l in r.stdout.splitlines()}
        self.assertIn("pronto", linhas["FE-A"])
        self.assertIn("backlog", linhas["FE-B"])   # liberada


if __name__ == "__main__":
    unittest.main()
