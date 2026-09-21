"""Testes do verbo `show` do orq-clickup (OA-14).

Existe porque o BRIEFING de toda sessão do papel único (`bin/orq`, passo 1)
manda rodar `orq-clickup show <id>` para ler a ordem de serviço inteira —
descrição E comentários, do mais antigo ao mais recente. O comando não
existia: só havia `desc` (só descrição) e `comment` (só escreve). Documentar
`show` sem ele existir seria afirmar um comportamento não provado — a regra
de ouro da própria OA-14 — por isso o comando nasce aqui, com prova.

Servidor falso em 127.0.0.1, apontado por CLICKUP_API_URL. Nenhuma chamada ao
ClickUp de verdade.
"""
import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / "bin" / "orq-clickup"

TAREFA = {
    "id": "868m168qp", "name": "A tela de frota trava sozinha",
    "status": {"status": "em progresso"},
    "markdown_description": "## Critério\n\nA tela não pode travar.",
}

# A API do ClickUp devolve os comentários do mais NOVO para o mais velho.
COMENTARIOS = {
    "comments": [
        {"id": "2", "date": "1788200000000",
         "user": {"username": "Fulano"}, "comment_text": "segundo comentário"},
        {"id": "1", "date": "1788100000000",
         "user": {"username": "Fulano"}, "comment_text": "primeiro comentário"},
    ]
}


class Falso(BaseHTTPRequestHandler):
    def do_GET(self):
        caminho = urlparse(self.path).path
        if caminho.endswith("/comment"):
            corpo = json.dumps(COMENTARIOS).encode()
        else:
            corpo = json.dumps(TAREFA).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass


class Show(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = HTTPServer(("127.0.0.1", 0), Falso)
        cls.porta = cls.servidor.server_address[1]
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def rodar(self, *args):
        ambiente = {
            **os.environ,
            "CLICKUP_API_URL": f"http://127.0.0.1:{self.porta}",
            "CLICKUP_API_KEY": "pk_token_de_teste",
        }
        return subprocess.run(
            ["node", str(CLI), "show", *args],
            capture_output=True, text=True, env=ambiente, timeout=30,
        )

    def test_traz_descricao_e_comentarios(self):
        r = self.rodar("868m168qp")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("A tela não pode travar", r.stdout)
        self.assertIn("primeiro comentário", r.stdout)
        self.assertIn("segundo comentário", r.stdout)
        self.assertIn("Fulano", r.stdout)

    def test_comentarios_saem_do_mais_antigo_para_o_mais_recente(self):
        # A API devolve do mais novo — inverter é o próprio ponto do comando.
        r = self.rodar("868m168qp")
        pos_primeiro = r.stdout.index("primeiro comentário")
        pos_segundo = r.stdout.index("segundo comentário")
        self.assertLess(pos_primeiro, pos_segundo)

    def test_sem_comentario_nenhum_nao_quebra(self):
        COMENTARIOS["comments"] = []
        try:
            r = self.rodar("868m168qp")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("(nenhum)", r.stdout)
        finally:
            COMENTARIOS["comments"] = [
                {"id": "2", "date": "1788200000000",
                 "user": {"username": "Fulano"}, "comment_text": "segundo comentário"},
                {"id": "1", "date": "1788100000000",
                 "user": {"username": "Fulano"}, "comment_text": "primeiro comentário"},
            ]

    def test_sem_argumento_ensina_o_uso(self):
        r = self.rodar()
        self.assertEqual(r.returncode, 1)
        self.assertIn("usage:", r.stderr)


if __name__ == "__main__":
    unittest.main()
