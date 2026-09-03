"""Testes das funções puras do motor.

NÃO existe suíte de testes do motor — foi decisão registrada na spec. Aqui só
entra função pura de análise de texto, que é barata de testar e cara de depurar
quando erra em silêncio dentro de uma decisão de capacidade: um erro aqui
serializa uma esteira inteira sem ninguém entender por quê.
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
# Registrar ANTES de executar: as dataclasses do motor procuram o próprio módulo
# em sys.modules ao resolver as anotações de tipo, e sem isto o carregamento
# morre com um erro que não tem nada a ver com o que está sendo testado.
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


class TetoPorEstagio(unittest.TestCase):
    """A forma da esteira: quantas sessões de CADA estágio cabem ao mesmo tempo.

    O teto global não exprime isso — ele deixaria todas as vagas irem para um
    estágio só.
    """

    def cfg(self, tetos=None, serial=None):
        return orq.Config(path=Path("/tmp/x.toml"), raw={
            "pipeline": {"name": "t", "list_id": "1", "repo": "/tmp"},
            "session": {"max_por_estagio": tetos or {}},
            "loop": {"serial_stages": serial or []},
        })

    def test_sem_teto(self):
        self.assertEqual(orq.teto_do_estagio(self.cfg(), "spec"), 0)

    def test_teto_declarado(self):
        self.assertEqual(orq.teto_do_estagio(self.cfg({"spec": 6}), "spec"), 6)

    def test_serial_vale_um(self):
        c = self.cfg(serial=["integrate"])
        self.assertEqual(orq.teto_do_estagio(c, "integrate"), 1)

    def test_serial_vence_teto_maior(self):
        # Ligar um nunca pode AFROUXAR o outro: duas integrações simultâneas
        # correriam uma contra a outra no branch de publicação.
        c = self.cfg({"integrate": 6}, serial=["integrate"])
        self.assertEqual(orq.teto_do_estagio(c, "integrate"), 1)

    def test_estagio_nulo(self):
        self.assertEqual(orq.teto_do_estagio(self.cfg({"spec": 6}), None), 0)


if __name__ == "__main__":
    unittest.main()
