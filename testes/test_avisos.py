"""Testes do roteamento de eventos e avisos (OA-11): o que avisa e o que cala.

Três camadas:
  * MÓDULO — bin/orq carregado via SourceFileLoader, testando o roteamento
    (`ROTEAMENTO_AVISOS`, `_repetido_ha_pouco`, `_avisos_cortados`,
    `_avisar_eventos_desde`) diretamente, com um `orq-avisar` de mentira
    (testes/fixtures/bin/orq-avisar) capturando cada chamada em
    `FAKE_AVISAR_LOG` — nenhum teste aqui entrega aviso de verdade.
  * PROCESSO — `orq hold`/`orq advance` como subprocesso, provando os três
    avisos do requisito de ponta a ponta.
  * GANCHO — `hooks/notificar.sh` como subprocesso, provando o silêncio: o
    gancho `Notification`/`Stop` SEMPRE passa `--canal local` ao entregador,
    nunca alcançando um destino externo (o "teste de ausência" que o spec
    exige nomeadamente).

Nenhum teste deste arquivo fala com a API real do Telegram nem depende de
~/.config/orquestrador/credenciais.env — mesmo que a máquina que roda a
suíte tenha credenciais reais configuradas.
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
HOOK = RAIZ / "hooks" / "notificar.sh"

os.environ.setdefault("ORQ_NOTIFY_CMD", str(FAKE_BIN / "orq-avisar"))

_loader = importlib.machinery.SourceFileLoader("orq", str(ORQ_BIN))
_spec = importlib.util.spec_from_loader("orq", _loader)
orq = importlib.util.module_from_spec(_spec)
sys.modules["orq"] = orq
_spec.loader.exec_module(orq)


def _ler_log(caminho: Path) -> list:
    if not caminho.exists():
        return []
    return [json.loads(l) for l in caminho.read_text().splitlines() if l.strip()]


# ==================================================================== MÓDULO

class ComUnidadeEAvisarDeMentira(unittest.TestCase):
    """Uma unidade declarada, e `ORQ_NOTIFY_CMD`/`FAKE_AVISAR_LOG` apontando
    para o `orq-avisar` de mentira — nenhum teste desta base entrega nada de
    verdade, nem quando `ORQ_AVISO_DESTINO`/credenciais reais existem na
    máquina, porque a entrega nem chega a acontecer: `_entregador_avisos()`
    é o de mentira."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.tmp.name) / "teste.db"
        con = orq.criar_banco(self.caminho)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.commit()
        con.close()

        self.log = Path(self.tmp.name) / "avisar.jsonl"
        self._notify_cmd_original = os.environ.get("ORQ_NOTIFY_CMD")
        self._fake_log_original = os.environ.get("FAKE_AVISAR_LOG")
        os.environ["ORQ_NOTIFY_CMD"] = str(FAKE_BIN / "orq-avisar")
        os.environ["FAKE_AVISAR_LOG"] = str(self.log)

    def tearDown(self):
        if self._notify_cmd_original is None:
            os.environ.pop("ORQ_NOTIFY_CMD", None)
        else:
            os.environ["ORQ_NOTIFY_CMD"] = self._notify_cmd_original
        if self._fake_log_original is None:
            os.environ.pop("FAKE_AVISAR_LOG", None)
        else:
            os.environ["FAKE_AVISAR_LOG"] = self._fake_log_original
        self.tmp.cleanup()

    def _entradas(self) -> list:
        return _ler_log(self.log)


class RoteamentoBasico(ComUnidadeEAvisarDeMentira):
    def test_despachada_avisa_com_o_titulo_certo(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso", tipo_evento="despachada")
        entradas = self._entradas()
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["titulo"], "tarefa iniciada por um agente")
        self.assertEqual(entradas[0]["unidade"], "FE-A")

    def test_bloqueada_avisa_com_o_motivo(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "bloqueado", tipo_evento="bloqueada",
                             motivo="esperando decisão de produto")
        entradas = self._entradas()
        # duas transições, uma só roteada ("transicao" genérico não está no
        # roteamento — só a explícita "bloqueada").
        roteadas = [e for e in entradas if e["titulo"] == "tarefa bloqueada"]
        self.assertEqual(len(roteadas), 1)
        self.assertIn("esperando decisão de produto", roteadas[0]["msg"])

    def test_declaracao_nunca_avisa(self):
        with orq.transacao(self.caminho) as con:
            orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        self.assertEqual(self._entradas(), [])

    def test_tipo_desconhecido_nunca_avisa(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "algo_que_nao_existe_no_roteamento")
        self.assertEqual(self._entradas(), [])

    def test_transicao_generica_sem_tipo_evento_nao_avisa(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")   # tipo_evento default: "transicao"
        self.assertEqual(self._entradas(), [])


class AvisoNaoAlteraEstado(ComUnidadeEAvisarDeMentira):
    def test_entregador_ausente_nao_impede_a_transicao(self):
        os.environ["ORQ_NOTIFY_CMD"] = "/caminho/que/nao/existe/avisar-fantasma"
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso", tipo_evento="despachada")
        con = orq.abrir_banco(self.caminho)
        status = con.execute(
            "SELECT status FROM unidade WHERE id = ?", (self.a,)).fetchone()["status"]
        ev = con.execute(
            "SELECT 1 FROM evento WHERE unidade_id = ? AND tipo = 'despachada'",
            (self.a,)).fetchone()
        con.close()
        self.assertEqual(status, "em_progresso")   # a transição aconteceu de verdade
        self.assertIsNotNone(ev)                    # e o evento ficou registrado


class AvisoEEstadoNaoDivergem(ComUnidadeEAvisarDeMentira):
    def test_toda_mensagem_entregue_tem_uma_linha_de_evento_correspondente(self):
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso", tipo_evento="despachada")
        entradas = self._entradas()
        self.assertEqual(len(entradas), 1)
        con = orq.abrir_banco(self.caminho)
        ev = con.execute(
            "SELECT tipo FROM evento WHERE unidade_id = ? AND tipo = 'despachada'",
            (self.a,)).fetchone()
        con.close()
        self.assertIsNotNone(ev)   # a mensagem entregue TEM uma linha em evento


class Antirrepeticao(ComUnidadeEAvisarDeMentira):
    def test_mesmo_par_nao_avisa_duas_vezes_em_menos_de_cinco_minutos(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "bloqueada", texto="motivo 1")
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "bloqueada", texto="motivo 2")
        entradas = self._entradas()
        self.assertEqual(len(entradas), 1)   # só a primeira

    def test_par_diferente_avisa_normalmente(self):
        con = orq.abrir_banco(self.caminho)
        b = orq.criar_unidade(con, "FE-B", clickup_id="2", titulo="b")
        con.commit()
        con.close()
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "bloqueada", texto="motivo")
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, b, "bloqueada", texto="motivo")   # unidade diferente
        self.assertEqual(len(self._entradas()), 2)

    def test_apos_a_janela_avisa_de_novo(self):
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "bloqueada", texto="motivo 1")
        # Recua o carimbo do primeiro evento em 10 minutos — simula "faz
        # tempo" sem esperar de verdade.
        con = orq.abrir_banco(self.caminho)
        con.execute(
            "UPDATE evento SET ts = datetime(ts, '-10 minutes') WHERE unidade_id = ?",
            (self.a,))
        con.commit()
        con.close()
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "bloqueada", texto="motivo 2")
        self.assertEqual(len(self._entradas()), 2)


class AvisosSilenciados(ComUnidadeEAvisarDeMentira):
    def test_config_corta_evento_operacional(self):
        with orq.transacao(self.caminho) as con:
            orq.definir_config(con, "avisos_silenciados", "recolhida")
        with orq.transacao(self.caminho) as con:
            orq.registrar_evento(con, self.a, "recolhida", texto="arranque falho")
        self.assertEqual(self._entradas(), [])

    def test_os_tres_obrigatorios_nunca_sao_cortaveis(self):
        with orq.transacao(self.caminho) as con:
            orq.definir_config(con, "avisos_silenciados", "despachada,pr_aberto,bloqueada")
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso", tipo_evento="despachada")
        self.assertEqual(len(self._entradas()), 1)   # a config tentou cortar; não cortou


class VigiaFalhouSoAvisaNaTerceira(ComUnidadeEAvisarDeMentira):
    """A regra 1 de antirrepetição do OA-11 ("vigia_falhou só avisa na
    terceira falha seguida") é satisfeita na origem (OA-08): `vigiar_prs` só
    grava `vigia_alerta` — o tipo que o roteamento entrega — exatamente na
    3ª falha seguida, nunca antes nem depois."""

    def setUp(self):
        super().setUp()
        with orq.transacao(self.caminho) as con:
            orq.transicionar(con, self.a, "em_progresso")
            orq.transicionar(con, self.a, "revisao")
            con.execute("UPDATE unidade SET pr_numero = 101 WHERE id = ?", (self.a,))
        con = orq.abrir_banco(self.caminho)
        con.execute("INSERT INTO config (chave, valor) VALUES ('github_repo', 'acme/x')")
        con.commit()
        con.close()
        self._path_original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{FAKE_BIN}:{self._path_original}"
        os.environ["FAKE_GH_PR_FAIL_101"] = "1"

    def tearDown(self):
        os.environ["PATH"] = self._path_original
        for k in ("FAKE_GH_PR_FAIL_101", "FAKE_GH_PRS_OK"):
            os.environ.pop(k, None)
        super().tearDown()

    def test_falhas_1_e_2_ficam_mudas_a_3a_avisa(self):
        for _ in range(3):
            with orq.transacao(self.caminho) as con:
                orq.vigiar_prs(con, "acme/x")
        entradas = self._entradas()
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["titulo"], "vigia de PR fora do ar")

    def test_falha_4_nao_repete_o_alerta(self):
        for _ in range(4):
            with orq.transacao(self.caminho) as con:
                orq.vigiar_prs(con, "acme/x")
        self.assertEqual(len(self._entradas()), 1)   # só a 3a — a 4a não soma outro alerta


class SemNotifySolto(unittest.TestCase):
    def test_grep_notify_nao_acha_chamada_solta(self):
        texto = ORQ_BIN.read_text()
        # Nenhum lugar deste arquivo usa a palavra "notify(" — nem precisa:
        # a origem única é `_avisar_eventos_desde`, em português como o
        # resto do arquivo. O critério ("só a função de emissão") vale por
        # construção: zero ocorrências é mais forte que "exatamente uma".
        self.assertNotIn("notify(", texto)

    def test_entregador_e_chamado_de_um_unico_lugar(self):
        texto = ORQ_BIN.read_text()
        # Uma ocorrência é a definição (`def _entregador_avisos() -> str:`);
        # a única chamada de verdade fica dentro de `_avisar_eventos_desde`.
        self.assertEqual(texto.count("_entregador_avisos()"), 2)
        self.assertEqual(texto.count("= _entregador_avisos()"), 1)


# =================================================================== PROCESSO

def orq_cli(db, *args, cwd=None, checar=True, env_extra=None):
    env = {**os.environ, "PATH": f"{FAKE_BIN}:{os.environ.get('PATH', '')}",
          "FAKE_GH_PRS_OK": "*", "ORQ_NOTIFY_CMD": str(FAKE_BIN / "orq-avisar"),
          **(env_extra or {})}
    r = subprocess.run(
        [sys.executable, str(ORQ_BIN), "--db", str(db), *args],
        cwd=cwd, capture_output=True, text=True, timeout=30, env=env)
    if checar and r.returncode != 0:
        raise AssertionError(
            f"orq {' '.join(args)} falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class TresAvisosDoRequisitoPontaAPonta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "e.db"
        con = orq.criar_banco(self.db)
        self.a = orq.criar_unidade(con, "FE-A", clickup_id="1", titulo="a")
        con.execute("INSERT INTO config (chave, valor) VALUES ('github_repo', 'acme/x')")
        con.commit()
        con.close()
        self.log = Path(self.tmp.name) / "avisar.jsonl"

        # As chamadas EM PROCESSO (orq.transacao direto) precisam do mesmo
        # ORQ_NOTIFY_CMD/FAKE_AVISAR_LOG que o subprocesso do `advance`
        # recebe por `env_extra` — senão os avisos "em processo" tentariam o
        # entregador real.
        self._notify_cmd_original = os.environ.get("ORQ_NOTIFY_CMD")
        self._fake_log_original = os.environ.get("FAKE_AVISAR_LOG")
        os.environ["ORQ_NOTIFY_CMD"] = str(FAKE_BIN / "orq-avisar")
        os.environ["FAKE_AVISAR_LOG"] = str(self.log)

    def tearDown(self):
        if self._notify_cmd_original is None:
            os.environ.pop("ORQ_NOTIFY_CMD", None)
        else:
            os.environ["ORQ_NOTIFY_CMD"] = self._notify_cmd_original
        if self._fake_log_original is None:
            os.environ.pop("FAKE_AVISAR_LOG", None)
        else:
            os.environ["FAKE_AVISAR_LOG"] = self._fake_log_original
        self.tmp.cleanup()

    def _entradas(self):
        return _ler_log(self.log)

    def test_iniciada_pr_aberto_e_bloqueada_chegam(self):
        # tarefa iniciada
        with orq.transacao(self.db) as con:
            orq.transicionar(con, self.a, "em_progresso", tipo_evento="despachada")
        # PR aberto (subprocesso — herda ORQ_NOTIFY_CMD/FAKE_AVISAR_LOG do
        # ambiente atual via `{**os.environ, ...}` em `orq_cli`)
        orq_cli(self.db, "advance", "FE-A", "--pr", "9")
        # tarefa bloqueada (revisão -> bloqueado é transição legal — mesmo
        # tipo "bloqueada" que o vigia (OA-08) usaria num PR fechado)
        with orq.transacao(self.db) as con:
            orq.transicionar(con, self.a, "bloqueado", tipo_evento="bloqueada",
                             motivo="fechado sem merge")

        titulos = {e["titulo"] for e in self._entradas()}
        self.assertIn("tarefa iniciada por um agente", titulos)
        self.assertIn("PR aberto por um agente", titulos)
        self.assertIn("tarefa bloqueada", titulos)


# ===================================================================== GANCHO

class GanchoNotificarSempreLocal(unittest.TestCase):
    """`hooks/notificar.sh` — o gancho Notification/Stop — nunca deixa a
    escolha de canal para ORQ_AVISO_DESTINO: sempre passa `--canal local`
    explícito ao entregador (OA-11)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "avisar.jsonl"
        self.logdir = Path(self.tmp.name) / "state"
        self.logdir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar_gancho(self, kind, payload=None):
        env = {**os.environ, "ORQ_UNIT": "FE-A", "ORQ_LOG_DIR": str(self.logdir),
              "ORQ_NOTIFY_CMD": str(FAKE_BIN / "orq-avisar"),
              "FAKE_AVISAR_LOG": str(self.log)}
        return subprocess.run(["bash", str(HOOK), kind], input=json.dumps(payload or {}),
                              capture_output=True, text=True, timeout=15, env=env)

    def test_notification_passa_canal_local(self):
        r = self._rodar_gancho("notification", {"message": "precisa de decisão"})
        self.assertEqual(r.returncode, 0)
        entradas = _ler_log(self.log)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["canal"], "local")

    def test_stop_passa_canal_local(self):
        r = self._rodar_gancho("stop", {})
        self.assertEqual(r.returncode, 0)
        entradas = _ler_log(self.log)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["canal"], "local")

    def test_notification_com_destino_telegram_globalmente_configurado_ainda_fica_local(self):
        """O cenário de risco que o spec nomeia: alguém padronizou
        ORQ_AVISO_DESTINO=telegram no ambiente. O gancho continua mudo
        porque `--canal local` vence qualquer variável de ambiente."""
        env = {**os.environ, "ORQ_UNIT": "FE-A", "ORQ_LOG_DIR": str(self.logdir),
              "ORQ_NOTIFY_CMD": str(FAKE_BIN / "orq-avisar"),
              "FAKE_AVISAR_LOG": str(self.log), "ORQ_AVISO_DESTINO": "telegram"}
        r = subprocess.run(["bash", str(HOOK), "notification"], input="{}",
                           capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(r.returncode, 0)
        entradas = _ler_log(self.log)
        self.assertEqual(entradas[0]["canal"], "local")

    def test_gancho_de_verdade_com_orq_avisar_de_verdade_nao_envia_nada(self):
        """Sem `ORQ_NOTIFY_CMD` — o `orq-avisar` REAL do repositório — e com
        credenciais de Telegram (falsas, mas presentes) e
        ORQ_AVISO_DESTINO=telegram explícito: ainda assim nada sai, porque
        `--canal local` intercepta antes de qualquer destino ser
        considerado. `avisos.log` é o único rastro."""
        credenciais = Path(self.tmp.name) / "credenciais.env"
        credenciais.write_text("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
        env = {**os.environ, "ORQ_UNIT": "FE-A", "ORQ_LOG_DIR": str(self.logdir),
              "ORQ_CREDENCIAIS": str(credenciais), "ORQ_AVISO_DESTINO": "telegram"}
        env.pop("ORQ_NOTIFY_CMD", None)
        r = subprocess.run(["bash", str(HOOK), "notification"],
                           input=json.dumps({"message": "precisa de decisão"}),
                           capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(r.returncode, 0)
        log = (self.logdir / "avisos.log").read_text()
        self.assertIn("precisa de você", log)   # o registro local aconteceu


if __name__ == "__main__":
    unittest.main()
