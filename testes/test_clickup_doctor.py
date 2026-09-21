"""Testes de `orq-clickup doctor` — a prova de ClickUp que OA-12 tira de
dentro de `orq doctor` (bin/orq): o motor não depende mais do ClickUp para
despachar, e a máquina continua disponível para quem ainda quiser provar a
conexão, com `--lista` opcional.

Servidor falso em 127.0.0.1, apontado por CLICKUP_API_URL — mesmo padrão de
test_clickup_attach.py e test_padronizar.py. Nenhuma chamada ao ClickUp de
verdade.
"""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / "bin" / "orq-clickup"

ESTADO = {}


class Falso(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/user":
            if ESTADO.get("user_falha"):
                self._responder(401, {"err": "unauthorized"})
                return
            self._responder(200, {"user": {"username": "teste", "email": "t@t.com", "id": 1}})
            return
        if self.path.startswith("/list/"):
            if ESTADO.get("list_falha"):
                self._responder(404, {"err": "not found"})
                return
            self._responder(200, {
                "id": "900", "name": "Lista de teste",
                "statuses": [{"status": s} for s in
                            ["backlog", "em progresso", "revisão", "bloqueado", "pronto"]],
            })
            return
        self._responder(404, {"err": "not found"})

    def _responder(self, code, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass


class Doctor(unittest.TestCase):
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
        ESTADO.clear()

    def _rodar(self, *args, sem_chave=False):
        ambiente = {**os.environ, "CLICKUP_API_URL": f"http://127.0.0.1:{self.porta}"}
        if not sem_chave:
            ambiente["CLICKUP_API_KEY"] = "pk_token_de_teste"
        else:
            ambiente.pop("CLICKUP_API_KEY", None)
            # `loadEnv()` cai para ~/.config/orquestrador/credenciais.env
            # quando a variável não está no ambiente — numa máquina que TEM
            # esse arquivo (a própria, por exemplo), "sem chave" só vira
            # "sem chave" de verdade com um HOME que não tem nada lá.
            self._lar_vazio = tempfile.TemporaryDirectory()
            self.addCleanup(self._lar_vazio.cleanup)
            ambiente["HOME"] = self._lar_vazio.name
        return subprocess.run(["node", str(CLI), "doctor", *args],
                              capture_output=True, text=True, env=ambiente, timeout=30)

    def test_autenticado_sem_lista_passa(self):
        r = self._rodar()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("teste", r.stdout)
        self.assertIn("pulei a checagem da lista", r.stdout)

    def test_autenticado_com_lista_que_responde_passa(self):
        r = self._rodar("--lista=900")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Lista de teste", r.stdout)
        self.assertIn("backlog", r.stdout)

    def test_sem_token_falha_mas_termina_a_prova_da_lista(self):
        r = self._rodar("--lista=900", sem_chave=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("✗", r.stdout)
        # mesmo sem token, a segunda prova (lista) ainda roda e aparece —
        # uma falha não pode engolir a outra.
        self.assertIn("Lista de teste", r.stdout)

    def test_lista_inacessivel_falha(self):
        ESTADO["list_falha"] = True
        r = self._rodar("--lista=900")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("✗", r.stdout)
        self.assertIn("lista responde", r.stdout)

    def test_autenticacao_falha_mas_nao_derruba_o_processo_por_excecao(self):
        ESTADO["user_falha"] = True
        r = self._rodar()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("✗", r.stdout)
        self.assertIn("token/autenticação", r.stdout)


if __name__ == "__main__":
    unittest.main()
