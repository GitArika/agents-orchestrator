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


class AmbienteDaSessaoTmux(unittest.TestCase):
    """O ambiente por unidade tem de viajar por `-e`, não por `env=`.

    `subprocess.run(env=...)` só alcança o CLIENTE tmux. Quando o servidor já
    está de pé — e ele fica de pé por dias, compartilhado por TODAS as esteiras
    da máquina — a sessão nova herda o ambiente do SERVIDOR, congelado na
    primeira sessão que o criou. Numa máquina com duas esteiras isso pôs quatro
    sessões vivas carregando o `ORQ_UNIT` de uma quinta, e sessões de uma esteira
    nascendo com o `ORQ_PIPELINE` da outra — `orq show` respondia "unidade não
    está no pipeline.toml" e havia risco real de escrever na lista errada.
    Foi relatado três vezes antes de alguém ver a causa.
    """

    def args(self, ambiente=None, cmd=None):
        if ambiente is None:
            ambiente = {"ORQ_UNIT": "CAT-04-integrate"}
        return orq.argumentos_new_session(
            "s-1", "/tmp/wt", ambiente, cmd or ["claude", "oi"])

    def test_cada_variavel_vai_por_e(self):
        a = self.args({"ORQ_UNIT": "CAT-04-integrate", "ORQ_PIPELINE": "/p.toml"})
        self.assertIn("-e", a)
        self.assertIn("ORQ_UNIT=CAT-04-integrate", a)
        self.assertIn("ORQ_PIPELINE=/p.toml", a)

    def test_cada_e_precede_o_seu_valor(self):
        a = self.args({"ORQ_UNIT": "X", "ORQ_PIPELINE": "/p.toml"})
        for i, v in enumerate(a):
            if v.startswith("ORQ_"):
                self.assertEqual(a[i - 1], "-e", f"{v} sem o -e à frente")

    def test_o_comando_vem_depois_das_opcoes(self):
        # tmux trata o primeiro argumento livre como o comando do painel: uma
        # opção depois dele viraria argumento do comando, em silêncio.
        a = self.args(cmd=["claude", "--settings", "/s.json"])
        self.assertEqual(a[-3:], ["claude", "--settings", "/s.json"])
        self.assertNotIn("-e", a[a.index("claude"):])

    def test_sessao_e_diretorio_declarados(self):
        a = self.args()
        self.assertEqual(a[:4], ["tmux", "new-session", "-d", "-s"])
        self.assertEqual(a[4], "s-1")
        self.assertEqual(a[a.index("-c") + 1], "/tmp/wt")

    def test_sem_ambiente_nao_inventa_e(self):
        self.assertNotIn("-e", self.args(ambiente={}))


class BriefingRenderiza(unittest.TestCase):
    """Toda ordem de serviço tem de fechar sem buraco, para todo estágio.

    O briefing é montado por `str.format`. Um campo novo no texto sem a chave
    correspondente no contexto levanta KeyError NA HORA DE LANCAR a sessão — a
    unidade ja saiu da fila, a worktree ja existe, e o erro aparece longe de
    quem o escreveu. Uma chave a mais e pior: passa calada e a sessao recebe uma
    instrucao pela metade.
    """

    def cfg(self, pipeline_extra=None):
        return orq.Config(path=Path("/tmp/x.toml"), raw={
            "pipeline": {"name": "t", "list_id": "1", "repo": "/tmp",
                         **(pipeline_extra or {})},
            "gates": {"setup": ["make setup"], "verify": ["make test"]},
        })

    def brief(self, chave, pipeline_extra=None):
        estagio = orq.Stage(key=chave, label=chave, queue="q", working="w",
                            done="d", idx=0)
        unidade = orq.Unit(id="868abc001", key="AA-01", title="titulo")
        return orq.build_brief(self.cfg(pipeline_extra), unidade, estagio,
                               Path("/tmp/wt"), "CU-868abc001-x")

    def test_todo_estagio_fecha(self):
        for chave in orq.BRIEFS:
            with self.subTest(estagio=chave):
                texto = self.brief(chave)
                self.assertNotIn("{", texto, "sobrou campo sem substituir")
                self.assertIn("AA-01", texto)

    def test_sem_declaracao_nao_manda_procurar_verificacao(self):
        # O padrao seguro: prova de menos, nunca uma prova que nao aconteceu.
        texto = self.brief("integrate")
        self.assertIn("NÃO declarou verificação automática", texto)
        self.assertNotIn("gh run list", texto)

    def test_declarada_vira_o_passo_7(self):
        texto = self.brief("integrate",
                           {"verificacao_automatica": "gh run list --limit 3"})
        self.assertIn("gh run list --limit 3", texto)
        self.assertNotIn("NÃO declarou", texto)

    def test_so_o_integrador_fala_de_verificacao(self):
        # Quem implementa nao publica: mandar conferir publicacao ali produz
        # sessao procurando o que nao e dela.
        self.assertNotIn("verificação automática", self.brief("implement"))


if __name__ == "__main__":
    unittest.main()
