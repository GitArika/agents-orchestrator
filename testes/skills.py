"""Confere a forma das skills. Uma skill com frontmatter errado não é acionada —
e ninguém descobre, porque não há erro: ela simplesmente nunca é usada."""
import pathlib, re, sys

falhou = False
raiz = pathlib.Path(__file__).resolve().parent.parent
skills = sorted(raiz.glob("skills/*/SKILL.md"))
for s in skills:
    t = s.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    if not m:
        print("SEM frontmatter:", s.parent.name); falhou = True; continue
    fm = m.group(1)
    for chave in ("name:", "description:"):
        if chave not in fm:
            print(f"{s.parent.name}: falta {chave}"); falhou = True
    nome = re.search(r"name:\s*(\S+)", fm)
    if nome and nome.group(1) != s.parent.name:
        print(f"{s.parent.name}: name '{nome.group(1)}' não bate com a pasta"); falhou = True
    desc = re.search(r"description:\s*(.+)", fm)
    if desc and len(desc.group(1)) < 120:
        print(f"{s.parent.name}: descrição curta demais para decidir acionamento"); falhou = True
    if len(t) < 800:
        print(f"{s.parent.name}: curta demais ({len(t)} caracteres)"); falhou = True

print(f"skills verificadas: {len(skills)}")
sys.exit(1 if falhou else 0)
