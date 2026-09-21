"""Testes das funções puras e independentes de banco do motor: leitura de
cgroup/memória (usadas por `orq host`) e a checagem de máquina que
`resolver_banco` (OA-03) reaproveita do antigo resolvedor de pipeline.toml.

O resto do motor (banco SQLite, verbos de declaração, máquina de estados) tem
suíte própria: testes/test_estado.py, testes/test_verbos.py,
testes/test_maquina.py.
"""
import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("orq", str(RAIZ / "bin" / "orq"))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


class ValorDeCgroup(unittest.TestCase):
    def test_numero(self):
        self.assertEqual(orq._cg_valor("19327352832\n"), 19327352832.0)

    def test_sem_teto(self):
        # "max" em memory.max significa SEM teto, não um número gigante.
        self.assertIsNone(orq._cg_valor("max\n"))

    def test_vazio_ou_lixo(self):
        self.assertIsNone(orq._cg_valor(""))
        self.assertIsNone(orq._cg_valor("nada"))


class EventoDeCgroup(unittest.TestCase):
    AMOSTRA = "low 0\nhigh 1104943\nmax 0\noom 0\noom_kill 0\n"

    def test_le_a_chave(self):
        self.assertEqual(orq._cg_evento(self.AMOSTRA, "high"), 1104943)
        self.assertEqual(orq._cg_evento(self.AMOSTRA, "oom_kill"), 0)

    def test_chave_ausente(self):
        self.assertEqual(orq._cg_evento(self.AMOSTRA, "inexistente"), 0)


class PressaoDeMemoriaDaApple(unittest.TestCase):
    def test_percentual(self):
        saida = "System-wide memory free percentage: 42%\n"
        self.assertEqual(orq._pressao_livre_pct(saida), 42)

    def test_sem_percentual(self):
        self.assertIsNone(orq._pressao_livre_pct("outra coisa"))


class DivergenciaDeMaquina(unittest.TestCase):
    """A esteira resolvida tem de governar o repositório onde você está.

    O `pipeline.toml` é versionado, então ele existe no repo E dentro de CADA
    worktree criada a partir dele. Em 04/09/2026, num Mac, a worktree da esteira de um
    épico continha o `pipeline.toml` da esteira que roda na VPS —
    `repo = /home/orq/repos/app-exemplo`, vinte unidades, outro objetivo. Qualquer
    `orq` ali sem `ORQ_PIPELINE` resolvia para a esteira ERRADA e seguia calado.

    A prova é comparar o repositório declarado com o repositório de verdade. O
    diretório git COMUM é o critério certo, e não o caminho do cwd: de dentro de
    uma worktree ele devolve o `.git` do repositório principal, que é o que a
    esteira declara. Comparar cwd com `repo` reprovaria toda worktree — isto é,
    toda sessão da esteira.
    """

    def test_bate_quando_e_a_mesma_arvore(self):
        self.assertIsNone(orq.divergencia_de_maquina(
            Path("/Users/eu/projeto"), Path("/Users/eu/projeto/.git")))

    def test_bate_de_dentro_de_uma_worktree(self):
        # A sessão roda em ~/worktrees/x/CU-123-y, cujo git comum é o do repo.
        self.assertIsNone(orq.divergencia_de_maquina(
            Path("/Users/eu/projeto"), Path("/Users/eu/projeto/.git")))

    def test_repo_declarado_nao_existe_nesta_maquina(self):
        # O caso que motivou tudo: config da VPS lida dentro do repo no Mac.
        motivo = orq.divergencia_de_maquina(
            Path("/home/orq/repos/app-exemplo"), Path("/Users/eu/projeto/.git"))
        self.assertIsNotNone(motivo)
        self.assertIn("/home/orq/repos/app-exemplo", motivo)

    def test_estou_noutro_repositorio(self):
        motivo = orq.divergencia_de_maquina(
            Path("/Users/eu/projeto"), Path("/Users/eu/OUTRO/.git"))
        self.assertIsNotNone(motivo)
        self.assertIn("OUTRO", motivo)

    def test_fora_de_qualquer_repositorio_nao_reprova(self):
        # `orq status` do diretório pessoal é uso legítimo: não há com o que
        # comparar, e recusar aqui quebraria quem só quer olhar.
        self.assertIsNone(orq.divergencia_de_maquina(
            Path("/home/orq/repos/app-exemplo"), None))


if __name__ == "__main__":
    unittest.main()
