"""Testes do verbo `attach` do orq-clickup.

Por que existe suíte para ISTO, quando o resto do orq-clickup não tem: o `attach`
é o único verbo que NÃO fala JSON. Ele monta um corpo multipart à mão, e a parte
que erra em silêncio — o nome do campo, o boundary, o cabeçalho que não pode ser
escrito à mão — devolve 200 do mesmo jeito quando está errada. Um teste que só
olhasse o código de saída passaria em cima de um anexo que nunca chegou.

Servidor falso em 127.0.0.1, apontado por CLICKUP_API_URL. Nenhuma chamada ao
ClickUp de verdade: anexar num cartão de verdade para testar deixaria lixo num
quadro que outras pessoas leem.
"""
import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / "bin" / "orq-clickup"

#: O que o servidor falso viu. Lista porque um `attach` de três capturas tem de
#: virar três requisições — e "mandou tudo numa só" é um jeito de errar.
RECEBIDAS: list[dict] = []


class Falso(BaseHTTPRequestHandler):
    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        RECEBIDAS.append({
            "caminho": self.path,
            "autorizacao": self.headers.get("Authorization"),
            "tipo": self.headers.get("Content-Type"),
            "corpo": self.rfile.read(tamanho),
        })
        corpo = json.dumps({
            "id": "anexo-1",
            "title": "captura.png",
            "url": "https://attachments.clickup.com/anexo-1",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass  # silêncio: a saída do teste é o que importa


class Attach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = HTTPServer(("127.0.0.1", 0), Falso)
        cls.porta = cls.servidor.server_address[1]
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        RECEBIDAS.clear()
        self.dir = TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def arquivo(self, nome, conteudo=b"\x89PNG\r\n\x1a\nfingimos-uma-captura"):
        p = Path(self.dir.name) / nome
        p.write_bytes(conteudo)
        return str(p)

    def rodar(self, *args):
        ambiente = {
            **os.environ,
            "CLICKUP_API_URL": f"http://127.0.0.1:{self.porta}",
            "CLICKUP_API_KEY": "pk_token_de_teste",
        }
        return subprocess.run(
            ["node", str(CLI), "attach", *args],
            capture_output=True, text=True, env=ambiente, timeout=30,
        )

    def test_manda_multipart_no_endereco_do_cartao(self):
        r = self.rodar("868m168qp", self.arquivo("captura-375.png"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(RECEBIDAS), 1)
        pedido = RECEBIDAS[0]
        self.assertEqual(pedido["caminho"], "/task/868m168qp/attachment")
        self.assertEqual(pedido["autorizacao"], "pk_token_de_teste")
        # O boundary tem de vir do próprio FormData. Escrever o Content-Type à
        # mão o apaga, e o ClickUp responde 200 sem gravar anexo nenhum.
        self.assertTrue(
            pedido["tipo"].startswith("multipart/form-data; boundary="),
            pedido["tipo"],
        )

    def test_o_campo_se_chama_attachment_e_leva_o_nome_do_arquivo(self):
        self.rodar("868m168qp", self.arquivo("captura-375.png"))
        corpo = RECEBIDAS[0]["corpo"]
        self.assertIn(b'name="attachment"', corpo)
        self.assertIn(b'filename="captura-375.png"', corpo)
        self.assertIn(b"fingimos-uma-captura", corpo)

    def test_cada_arquivo_vira_uma_requisicao(self):
        r = self.rodar(
            "868m168qp",
            self.arquivo("captura-375.png"),
            self.arquivo("captura-768.png"),
            self.arquivo("captura-1440.png"),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(RECEBIDAS), 3)

    def test_arquivo_que_falta_para_antes_de_subir_qualquer_coisa(self):
        # A ordem importa: um `attach` de três capturas em que a segunda não
        # existe não pode deixar a primeira publicada e morrer no meio. Meio
        # anexo num cartão é pior que nenhum — quem lê não sabe que falta.
        r = self.rodar(
            "868m168qp",
            self.arquivo("existe.png"),
            str(Path(self.dir.name) / "nao-existe.png"),
        )
        self.assertEqual(r.returncode, 1)
        self.assertEqual(RECEBIDAS, [])
        self.assertIn("nao-existe.png", r.stderr)

    def test_sem_argumento_ensina_o_uso(self):
        r = self.rodar()
        self.assertEqual(r.returncode, 1)
        self.assertIn("uso:", r.stderr)


if __name__ == "__main__":
    unittest.main()
