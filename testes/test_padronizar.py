"""Testes de `orq-clickup padronizar` — o espelho de cinco status (OA-07).

Servidor falso em 127.0.0.1, apontado por CLICKUP_API_URL — nenhuma chamada
ao ClickUp de verdade, mesmo padrão de test_clickup_attach.py. O estado do
servidor (status atuais, override_statuses, tarefas por página) é montado
por teste, e cada requisição fica registrada para provar tanto O QUE foi
escrito quanto O QUE NÃO foi (a simulação sem --aplicar não pode enviar
PUT nenhum).
"""
import json
import os
import re
import subprocess
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / "bin" / "orq-clickup"

ESTADO = {}
REQUISICOES = []


class Falso(BaseHTTPRequestHandler):
    def do_GET(self):
        caminho = self.path.split("?")[0]
        REQUISICOES.append({"metodo": "GET", "caminho": self.path})
        if re.match(r"^/list/[\w-]+/task$", caminho):
            self._tarefas()
        elif re.match(r"^/list/[\w-]+$", caminho):
            self._lista()
        else:
            self._responder(404, {"err": "not found"})

    def do_PUT(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        REQUISICOES.append({"metodo": "PUT", "caminho": self.path, "corpo": corpo})
        if not ESTADO.get("put_ignora"):
            ESTADO["statuses"] = [s["status"] for s in corpo.get("statuses", [])]
            ESTADO["override_statuses"] = corpo.get("override_statuses", True)
        self._responder(200, {"id": ESTADO["list_id"]})

    def _lista(self):
        self._responder(200, {
            "id": ESTADO["list_id"], "name": ESTADO.get("list_name", "Lista de teste"),
            "statuses": [{"status": s} for s in ESTADO["statuses"]],
            "override_statuses": ESTADO.get("override_statuses", True),
            "folder": {"name": ESTADO.get("folder_name", "Pasta")},
            "space": {"name": ESTADO.get("space_name", "Espaço")},
        })

    def _tarefas(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        page = int((qs.get("page") or ["0"])[0])
        paginas = ESTADO.get("paginas_tarefas", [[]])
        if page < len(paginas):
            tarefas, last = paginas[page], page == len(paginas) - 1
        else:
            tarefas, last = [], True
        self._responder(200, {"tasks": tarefas, "last_page": last})

    def _responder(self, code, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass


CINCO = ["backlog", "em progresso", "revisão", "bloqueado", "pronto"]


class Padronizar(unittest.TestCase):
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
        REQUISICOES.clear()
        ESTADO.clear()
        ESTADO.update({
            "list_id": "900", "statuses": ["backlog", "pronto"],
            "override_statuses": True, "paginas_tarefas": [[]],
        })

    def _rodar(self, *args):
        ambiente = {
            **os.environ,
            "CLICKUP_API_URL": f"http://127.0.0.1:{self.porta}",
            "CLICKUP_API_KEY": "pk_token_de_teste",
        }
        return subprocess.run(
            ["node", str(CLI), "padronizar", *args],
            capture_output=True, text=True, env=ambiente, timeout=30)

    def _puts(self):
        return [r for r in REQUISICOES if r["metodo"] == "PUT"]

    # ---- o essencial --------------------------------------------------

    def test_lista_limpa_fica_com_exatamente_cinco(self):
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("exatamente os cinco", r.stdout)
        self.assertEqual(len(self._puts()), 1)
        enviados = [s["status"] for s in self._puts()[0]["corpo"]["statuses"]]
        self.assertEqual(enviados, CINCO)
        self.assertTrue(self._puts()[0]["corpo"]["override_statuses"])

    def test_sem_cinco_recusa(self):
        r = self._rodar("900", "--aplicar")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uso:", r.stderr)
        self.assertEqual(self._puts(), [])

    def test_sem_id_recusa(self):
        r = self._rodar("--cinco")
        self.assertNotEqual(r.returncode, 0)

    # ---- simulação ------------------------------------------------------

    def test_sem_aplicar_e_simulacao_nao_escreve(self):
        r = self._rodar("900", "--cinco")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("simulação", r.stdout)
        self.assertEqual(self._puts(), [])

    # ---- herança de status ------------------------------------------------

    def test_lista_que_herda_recusa_sem_substituir(self):
        ESTADO["override_statuses"] = False
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("HERDA", r.stdout)
        self.assertIn("substituir", r.stderr)
        self.assertEqual(self._puts(), [])

    def test_lista_que_herda_aplica_com_substituir(self):
        ESTADO["override_statuses"] = False
        r = self._rodar("900", "--cinco", "--aplicar", "--substituir")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self._puts()), 1)

    # ---- a API não é confiável, sem reler (aprendizado nº 17) --------------

    def test_api_responde_sucesso_sem_aplicar_e_o_comando_recusa(self):
        ESTADO["put_ignora"] = True   # PUT responde 200, mas o estado não muda
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FALHOU", r.stderr)
        self.assertIn("Não confie na resposta", r.stderr)

    # ---- conversão consciente: recusa tarefa órfã --------------------------

    def test_recusa_tarefa_em_status_orfao_mesmo_nome(self):
        ESTADO["paginas_tarefas"] = [[
            {"id": "t1", "name": "tarefa presa", "status": {"status": "aguardando revisão"}},
        ]]
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aguardando revisão", r.stdout)
        self.assertIn("tarefa presa", r.stdout)
        self.assertEqual(self._puts(), [])

    def test_recusa_mesmo_sem_aplicar(self):
        # "recusa" é do comando, não só da escrita — a pessoa precisa saber
        # ANTES de decidir aplicar.
        ESTADO["paginas_tarefas"] = [[
            {"id": "t1", "name": "presa", "status": {"status": "parado"}},
        ]]
        r = self._rodar("900", "--cinco")
        self.assertNotEqual(r.returncode, 0)

    def test_tarefa_em_status_canonico_nao_e_orfa(self):
        ESTADO["paginas_tarefas"] = [[
            {"id": "t1", "name": "em dia", "status": {"status": "em progresso"}},
        ]]
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_conta_tarefa_orfa_na_segunda_pagina(self):
        ESTADO["paginas_tarefas"] = [
            [{"id": f"t{i}", "name": f"aberta {i}", "status": {"status": "backlog"}}
             for i in range(3)],
            [{"id": "t99", "name": "presa na pagina 2", "status": {"status": "revisando"}}],
        ]
        r = self._rodar("900", "--cinco", "--aplicar")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("presa na pagina 2", r.stdout)
        self.assertEqual(self._puts(), [])


if __name__ == "__main__":
    unittest.main()
