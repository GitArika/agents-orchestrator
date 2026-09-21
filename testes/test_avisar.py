"""Testes do canal de aviso pelo Telegram (OA-10): bin/orq-avisar.

Duas camadas:
  * MÓDULO — carrega bin/orq-avisar via SourceFileLoader e testa as funções
    puras (escapar HTML, formatação, seleção de destino padrão, leitura de
    credencial), mockando `urllib.request.urlopen` — sem tocar a rede nem a
    API real do Telegram.
  * PROCESSO — roda o script como subprocesso, com ORQ_CREDENCIAIS e
    ORQ_LOG_DIR apontando para diretórios temporários, para provar as duas
    regras que o arquivo não pode quebrar: nunca sai != 0 (exceto --testar,
    que é o próprio diagnóstico) e o registro em arquivo acontece antes de
    qualquer entrega.

Nenhum teste aqui fala com a API real do Telegram nem dispara notificação de
sistema — ORQ_AVISO_DESTINO é sempre explícito, nunca deixado para o padrão
dinâmico escolher `macos` numa máquina que É um Mac.

A entrega de verdade (mensagem chegando na conversa configurada em
~/.config/orquestrador/credenciais.env) foi confirmada manualmente com
`orq-avisar --testar` antes deste arquivo existir — não repetida aqui de
propósito, para a suíte não depender de rede nem enviar mensagem a cada
rodada de teste.

"A sessão não lê a credencial" (um dos critérios de aceite do spec) é a
cerca, não este arquivo — provado por testes/cerca.sh.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO = RAIZ / "bin" / "orq-avisar"

_loader = importlib.machinery.SourceFileLoader("orq_avisar", str(CAMINHO))
_spec = importlib.util.spec_from_loader("orq_avisar", _loader)
av = importlib.util.module_from_spec(_spec)
sys.modules["orq_avisar"] = av
_spec.loader.exec_module(av)


def _resposta(corpo: dict) -> io.BytesIO:
    """Um `urlopen(...)` de mentira: BytesIO já é seu próprio context manager,
    então serve tanto para `with urlopen(...) as r` quanto para `json.load`."""
    return io.BytesIO(json.dumps(corpo).encode())


class EscaparHtml(unittest.TestCase):
    def test_escapa_os_tres_caracteres_de_marcacao(self):
        self.assertEqual(av._escapar_html("a & b < c > d"),
                         "a &amp; b &lt; c &gt; d")

    def test_nao_escapa_underscore(self):
        # É a razão de existir do HTML em vez de Markdown neste arquivo.
        self.assertEqual(av._escapar_html("CU-123-feature_branch"),
                         "CU-123-feature_branch")

    def test_preserva_emoji(self):
        self.assertIn("🔔", av._escapar_html("🔔 aviso"))


class CredencialTemporaria(unittest.TestCase):
    """Base: um credenciais.env de mentira, trocado no próprio módulo
    importado — mais direto que reimportar com ORQ_CREDENCIAIS a cada teste."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._original = av.CREDENCIAIS
        self.arquivo = Path(self.tmp.name) / "credenciais.env"
        av.CREDENCIAIS = self.arquivo

    def tearDown(self):
        av.CREDENCIAIS = self._original
        self.tmp.cleanup()

    def _escrever(self, texto: str):
        self.arquivo.write_text(texto)


class LerCredencialTelegram(CredencialTemporaria):
    def test_le_token_e_chat_id(self):
        self._escrever("TELEGRAM_BOT_TOKEN=123:ABC\nTELEGRAM_CHAT_ID=-100999\n")
        self.assertEqual(av.token_telegram(), "123:ABC")
        self.assertEqual(av.chat_id_telegram(), "-100999")

    def test_ignora_comentario_e_linha_sem_igual(self):
        self._escrever("# comentário\nnao tem igual\nTELEGRAM_BOT_TOKEN=x\n"
                       "TELEGRAM_CHAT_ID=y\n")
        self.assertEqual(av.token_telegram(), "x")

    def test_arquivo_ausente_levanta(self):
        with self.assertRaises(RuntimeError):
            av.token_telegram()

    def test_chave_ausente_levanta(self):
        self._escrever("CLICKUP_API_KEY=pk_x\n")
        with self.assertRaises(RuntimeError):
            av.token_telegram()

    def test_chave_vazia_levanta(self):
        self._escrever("TELEGRAM_BOT_TOKEN=\n")
        with self.assertRaises(RuntimeError):
            av.token_telegram()

    def test_aspas_sao_removidas(self):
        self._escrever('TELEGRAM_BOT_TOKEN="123:ABC"\n')
        self.assertEqual(av.token_telegram(), "123:ABC")


class DestinoPadrao(CredencialTemporaria):
    def test_telegram_quando_as_duas_credenciais_existem(self):
        self._escrever("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
        self.assertEqual(av._destino_padrao(), "telegram")

    def test_macos_quando_faltam_credenciais(self):
        self._escrever("CLICKUP_API_KEY=pk_x\n")
        self.assertEqual(av._destino_padrao(), "macos")

    def test_macos_quando_arquivo_nao_existe(self):
        self.assertEqual(av._destino_padrao(), "macos")


class ParaTelegram(CredencialTemporaria):
    def setUp(self):
        super().setUp()
        self._escrever("TELEGRAM_BOT_TOKEN=123:ABC\nTELEGRAM_CHAT_ID=-100999\n")

    def test_devolve_o_message_id_quando_ok(self):
        with patch("orq_avisar.urllib.request.urlopen",
                   return_value=_resposta({"ok": True, "result": {"message_id": 7}})):
            self.assertEqual(av.para_telegram("FE-01", "título", "corpo"),
                             "message_id=7")

    def test_ok_false_levanta_com_a_descricao(self):
        with patch("orq_avisar.urllib.request.urlopen",
                   return_value=_resposta({"ok": False, "description": "chat not found"})):
            with self.assertRaises(RuntimeError) as ctx:
                av.para_telegram("", "título", "corpo")
            self.assertIn("chat not found", str(ctx.exception))

    def test_http_error_e_convertido_com_o_detalhe(self):
        corpo = json.dumps({"description": "Unauthorized"}).encode()
        erro = urllib.error.HTTPError(
            "https://api.telegram.org/x", 401, "Unauthorized", {}, io.BytesIO(corpo))
        try:
            with patch("orq_avisar.urllib.request.urlopen", side_effect=erro):
                with self.assertRaises(RuntimeError) as ctx:
                    av.para_telegram("", "título", "corpo")
                self.assertIn("401", str(ctx.exception))
        finally:
            erro.close()

    def test_rede_fora_do_ar_levanta_uma_excecao_normal(self):
        with patch("orq_avisar.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timed out")):
            with self.assertRaises(Exception):
                av.para_telegram("", "título", "corpo")

    def test_monta_ate_quatro_linhas_com_titulo_em_negrito(self):
        capturado = {}

        def fake_urlopen(req, timeout=None):
            capturado["corpo"] = json.loads(req.data.decode())
            return _resposta({"ok": True, "result": {"message_id": 1}})

        os.environ["ORQ_AVISO_RODAPE"] = "esteira na VPS — orq status"
        try:
            with patch("orq_avisar.urllib.request.urlopen", side_effect=fake_urlopen):
                av.para_telegram("FE-03-implement", "▶ FE-03 iniciada",
                                 "Implementar o seletor de período")
        finally:
            del os.environ["ORQ_AVISO_RODAPE"]

        texto = capturado["corpo"]["text"]
        linhas = texto.split("\n")
        self.assertEqual(linhas[0], "<b>▶ FE-03 iniciada</b>")
        self.assertEqual(linhas[1], "Implementar o seletor de período")
        self.assertIn("FE-03-implement", linhas[2])
        self.assertIn("orq status", linhas[3])
        self.assertEqual(capturado["corpo"]["parse_mode"], "HTML")
        self.assertEqual(capturado["corpo"]["chat_id"], "-100999")

    def test_escapa_caracteres_especiais_no_corpo_enviado(self):
        capturado = {}

        def fake_urlopen(req, timeout=None):
            capturado["corpo"] = json.loads(req.data.decode())
            return _resposta({"ok": True, "result": {"message_id": 1}})

        with patch("orq_avisar.urllib.request.urlopen", side_effect=fake_urlopen):
            av.para_telegram("", "título <script> & cia", "branch feature_x & <y>")
        texto = capturado["corpo"]["text"]
        self.assertNotIn("<script>", texto)
        self.assertIn("&lt;script&gt;", texto)
        self.assertIn("feature_x", texto)   # underscore intacto


class Testar(CredencialTemporaria):
    def test_sem_credencial_devolve_1(self):
        self.assertEqual(av.testar(), 1)

    def test_com_credencial_e_api_ok_devolve_0(self):
        self._escrever("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
        with patch("orq_avisar.urllib.request.urlopen",
                   return_value=_resposta({"ok": True, "result": {"message_id": 41}})):
            self.assertEqual(av.testar(), 0)

    def test_com_credencial_mas_api_falha_devolve_1(self):
        self._escrever("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
        with patch("orq_avisar.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("sem rede")):
            self.assertEqual(av.testar(), 1)


class ComoSubprocesso(unittest.TestCase):
    """O script de verdade, de fora — prova o contrato de saída e o rastro em
    disco sem depender de mockar nada por dentro."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.credenciais = raiz / "credenciais.env"
        self.logdir = raiz / "state"
        self.logdir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar(self, *args, env_extra=None):
        env = {**os.environ, "ORQ_CREDENCIAIS": str(self.credenciais),
              "ORQ_LOG_DIR": str(self.logdir), **(env_extra or {})}
        return subprocess.run([sys.executable, str(CAMINHO), *args],
                              capture_output=True, text=True, timeout=30, env=env)

    def test_sem_titulo_nem_mensagem_nao_faz_nada_e_sai_0(self):
        r = self._rodar()
        self.assertEqual(r.returncode, 0)

    def test_credencial_ausente_nao_quebra_e_registra(self):
        r = self._rodar("título de teste", "mensagem de teste",
                        env_extra={"ORQ_AVISO_DESTINO": "telegram"})
        self.assertEqual(r.returncode, 0)
        log = (self.logdir / "avisos.log").read_text()
        self.assertIn("título de teste", log)
        self.assertIn("não entreguei", r.stdout + r.stderr)

    def test_destino_desconhecido_nao_quebra(self):
        r = self._rodar("t", "m", env_extra={"ORQ_AVISO_DESTINO": "fax"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("desconhecido", r.stdout + r.stderr)

    def test_credencial_nao_vaza_para_o_registro(self):
        self.credenciais.write_text(
            "TELEGRAM_BOT_TOKEN=SEGREDO_QUE_NAO_PODE_VAZAR\nTELEGRAM_CHAT_ID=-1\n")
        self._rodar("t", "m", env_extra={"ORQ_AVISO_DESTINO": "telegram"})
        log = (self.logdir / "avisos.log").read_text()
        self.assertNotIn("SEGREDO_QUE_NAO_PODE_VAZAR", log)

    def test_testar_sem_credencial_sai_1(self):
        r = self._rodar("--testar")
        self.assertEqual(r.returncode, 1)
        self.assertIn("não configurado", r.stdout + r.stderr)

    def test_canal_local_nunca_tenta_entrega_mesmo_com_telegram_configurado(self):
        """OA-11: o teste de ausência que protege o requisito de silêncio —
        mesmo com credencial de verdade e ORQ_AVISO_DESTINO=telegram
        explícito (o cenário de risco que o spec nomeia: alguém padronizou o
        destino globalmente), `--canal local` nunca chega a tentar
        `para_telegram`. Prova: nenhuma linha 'telegram:' no stdout — é o que
        apareceria SE a entrega fosse tentada, sucesso ou falha."""
        self.credenciais.write_text("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
        r = self._rodar("--canal", "local", "título", "mensagem",
                        env_extra={"ORQ_AVISO_DESTINO": "telegram"})
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("telegram:", r.stdout)
        self.assertNotIn("entreguei", r.stdout + r.stderr)   # nem sucesso, nem falha — nem tentou

    def test_canal_local_ainda_registra(self):
        """--canal local pula a ENTREGA, não o registro — avisos.log é o
        canal que sempre existe."""
        self._rodar("--canal", "local", "título de teste", "mensagem de teste")
        log = (self.logdir / "avisos.log").read_text()
        self.assertIn("título de teste", log)

    def test_canal_local_funciona_com_titulo_e_mensagem_antes_ou_depois(self):
        r = self._rodar("título", "mensagem", "--canal", "local",
                        env_extra={"ORQ_AVISO_DESTINO": "macos"})
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("macos:", r.stdout)


if __name__ == "__main__":
    unittest.main()
