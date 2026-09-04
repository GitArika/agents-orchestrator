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


class EscolhaDaEsteira(unittest.TestCase):
    """Config que não é desta máquina não deve nem entrar na disputa.

    Antes, subir os diretórios tinha prioridade sobre tudo que viesse depois. Como
    o `pipeline.toml` é VERSIONADO, quem estivesse dentro do repositório do
    do projeto num Mac recebia a esteira da VPS — e a esteira do próprio épico,
    guardada fora do repositório, nunca era consultada. Avisar não bastava: o
    comando continuava inútil.
    """

    MAC = Path("/Users/eu/app-exemplo/.git")
    VPS_CFG = (Path("/repo/.orchestrator/pipeline.toml"), Path("/home/orq/repos/app-exemplo"))
    SBX_CFG = (Path("/Users/eu/.config/orquestrador/esteiras/sbx.toml"),
               Path("/Users/eu/app-exemplo"))

    def test_descarta_a_de_outra_maquina_e_fica_com_a_daqui(self):
        self.assertEqual(
            orq.esteiras_desta_maquina([self.VPS_CFG, self.SBX_CFG], self.MAC),
            [self.SBX_CFG[0]])

    def test_na_vps_a_do_repositorio_serve(self):
        vps = Path("/home/orq/repos/app-exemplo/.git")
        self.assertEqual(
            orq.esteiras_desta_maquina([self.VPS_CFG], vps), [self.VPS_CFG[0]])

    def test_duas_da_mesma_maquina_nao_se_desempatam_sozinhas(self):
        outra = (Path("/Users/eu/.config/orquestrador/esteiras/outro-epico.toml"),
                 Path("/Users/eu/app-exemplo"))
        self.assertEqual(len(orq.esteiras_desta_maquina(
            [self.SBX_CFG, outra], self.MAC)), 2)

    def test_fora_de_repositorio_nao_escolhe_por_voce(self):
        # Sem repositório não há como discriminar; escolher aqui seria adivinhar.
        self.assertEqual(orq.esteiras_desta_maquina(
            [self.VPS_CFG, self.SBX_CFG], None), [])


class SoltaAMaoNaoEFalta(unittest.TestCase):
    """`orq release` feito por uma pessoa não pode virar falta na unidade.

    `release` devolve a unidade ao status de onde ela saiu — um status de
    TRABALHO, porque foi ali que ela travou. Sem sessão viva, o ciclo seguinte a
    classifica como `stalled` e conta um arranque falho. Com `max_strikes = 2`,
    duas liberações legítimas mandam para a quarentena uma unidade que nunca
    falhou.

    O laço já protegia o desbloqueio que ELE mesmo faz (`--until-unit`), pelo
    conjunto preenchido dentro do próprio ciclo. A liberação humana acontece em
    outra invocação, então aquele conjunto está vazio quando ela é avaliada —
    ficou de fora. Em 04/09/2026, duas unidades foram soltas à mão na VPS e
    cairiam nisso.
    """

    def test_arranque_falho_de_verdade_conta(self):
        self.assertTrue(orq.conta_falta("id1", "FE-01", [], []))

    def test_solta_pelo_proprio_laco_nao_conta(self):
        self.assertFalse(orq.conta_falta("id1", "FE-01", ["FE-01"], []))

    def test_solta_a_mao_nao_conta(self):
        self.assertFalse(orq.conta_falta("id1", "FE-01", [], ["id1"]))

    def test_o_perdao_e_da_unidade_certa(self):
        # Token de outra unidade não desculpa esta.
        self.assertTrue(orq.conta_falta("id1", "FE-01", ["DS-02"], ["id9"]))


class EscolhaExplicitaVence(unittest.TestCase):
    """Quem NOMEIA a esteira já resolveu a ambiguidade que o portão existe para pegar.

    O portão nasceu para um perigo específico: a resolução IMPLÍCITA — subir os
    diretórios e achar o arquivo versionado de outra máquina, ou cair no cache da
    última esteira usada — escolher por você e você não perceber.

    Quando a pessoa passa `--pipeline` ou exporta `ORQ_PIPELINE`, não há o que
    perceber: ela disse qual quer. Recusar ali é falso positivo, e pior, a
    mensagem mandava fazer exatamente o que continuaria sendo recusado — em
    04/09/2026 alguém seguiu o conselho e bateu na mesma parede.

    O `orq run` age sobre a worktree da esteira, não sobre o diretório de onde foi
    chamado; estar noutro repositório é irrelevante quando a escolha foi dita.
    """

    def test_implicita_e_divergente_recusa(self):
        self.assertTrue(orq.deve_recusar(explicita=False, so_le=False, divergente=True))

    def test_explicita_nao_recusa_mesmo_divergente(self):
        self.assertFalse(orq.deve_recusar(explicita=True, so_le=False, divergente=True))

    def test_leitura_nunca_recusa(self):
        self.assertFalse(orq.deve_recusar(explicita=False, so_le=True, divergente=True))

    def test_sem_divergencia_nada_a_recusar(self):
        self.assertFalse(orq.deve_recusar(explicita=False, so_le=False, divergente=False))


class ComandoSoLe(unittest.TestCase):
    """Ler a esteira errada não estraga nada; AGIR nela, sim.

    Recusar `orq board` de outro diretório é fricção sem ganho, e guarda que
    atrapalha é guarda que alguém desliga. O corte é entre olhar e escrever.
    """

    def test_leitura(self):
        for c in ("board", "next", "status", "show", "log", "capacity", "brief"):
            self.assertTrue(orq.comando_so_le(c), c)

    def test_escrita(self):
        for c in ("run", "dispatch", "advance", "reject", "hold", "note",
                  "describe", "tick", "loop", "reset", "sweep", "stop"):
            self.assertFalse(orq.comando_so_le(c), c)

    def test_desconhecido_e_tratado_como_escrita(self):
        # Comando novo entra pelo lado seguro: quem acrescentar um que só lê
        # acrescenta o nome na lista, de propósito.
        self.assertFalse(orq.comando_so_le("comando-que-ainda-nao-existe"))


class UnidadesDisputadas(unittest.TestCase):
    """Duas esteiras na mesma lista não podem declarar a mesma unidade.

    Elas não brigam por status — o ClickUp já serializa isso. Brigam por
    DESPACHO: duas máquinas lançam a mesma tarefa, criam o mesmo branch e
    duplicam o trabalho. Só dá para pegar comparando as declarações.
    """

    def test_sem_sobreposicao(self):
        self.assertEqual(orq.unidades_disputadas(
            {"a": ["1", "2"]}, {"b": ["3", "4"]}), [])

    def test_lista_diferente_nao_disputa(self):
        # Mesmo id de tarefa em listas diferentes é coincidência impossível,
        # mas a checagem é por lista de propósito: esteiras de projetos
        # distintos não têm nada a se dizer.
        self.assertEqual(orq.unidades_disputadas(
            {"a": ["1"]}, {"b": ["1"]}), [])

    def test_sobreposicao_e_apontada(self):
        self.assertEqual(orq.unidades_disputadas(
            {"L": ["1", "2", "3"]}, {"L": ["2", "3", "9"]}), ["2", "3"])


if __name__ == "__main__":
    unittest.main()
