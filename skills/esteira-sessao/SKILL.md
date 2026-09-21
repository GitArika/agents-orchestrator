---
name: esteira-sessao
description: Use quando esta sessão foi lançada por uma esteira e recebeu uma ordem de serviço — o contrato de trabalho de uma sessão trabalhadora: ler a ordem, fazer uma coisa só, passar pelos portões declarados e terminar por exatamente um dos três caminhos previstos. Use também quando alguém pedir para executar uma unidade da esteira à mão, quando você estiver numa cópia de trabalho da esteira e não souber como encerrar o que fez, ou quando um comando seu for barrado pela cerca e você precisar saber o que fazer em vez de insistir.
---

# O contrato da sessão trabalhadora

Você foi lançada por uma esteira. Isto vale para você.

## 1. A ordem de serviço é a sua única fonte

O texto que você recebeu ao nascer é o escopo inteiro. Nada fora dele.

Se você descobrir outro problema no caminho — e vai descobrir —, **registre e siga**. Não
conserte de passagem. Escopo alargado é motivo de reprovação, e com razão: quem revisa
precisa conseguir julgar uma coisa, não três.

```bash
orq note <UNIDADE> --text "Achei X, fora do escopo desta unidade. Vale abrir."
```

## 2. Prepare o ambiente com o que a ordem manda

A cópia de trabalho nasce **sem dependências instaladas** e sem os arquivos de ambiente que
o git ignora. Os comandos de preparo estão na sua ordem de serviço. Rode-os antes de
qualquer outra coisa, senão os portões falham por motivo errado e você vai depurar o
problema errado.

## 3. Os portões rodam antes de concluir

Também estão na ordem. Rode todos, e ponha o resultado no comentário da tarefa. Portão
vermelho não se contorna: ou você conserta, ou a unidade não avança.

## 4. Como esta sessão termina

Termine por **exatamente um** destes caminhos:

```bash
orq advance <UNIDADE>                      # concluí
orq reject  <UNIDADE> --file achados.md    # reprovei: o defeito está no trabalho
orq reject  <UNIDADE> --to spec --file a.md   # o defeito está na especificação
orq hold    <UNIDADE> --reason "..."       # travei em algo que só uma pessoa resolve
```

**Encerrar sem nenhum deles deixa a unidade num status de trabalho, e a esteira lê isso
como sessão morta.** A unidade some do radar e alguém precisa resgatá-la à mão. Isto já
aconteceu; é a razão de este parágrafo existir.

O motivo do `hold` precisa dizer o que trava, com pelo menos vinte caracteres — é validado.
"Não consegui" não é motivo.

Se o que trava é **outra unidade**, e não uma pessoa, diga isso: a esteira solta sozinha
quando ela avançar, e ninguém precisa lembrar de nada.

```bash
orq hold <UNIDADE> --reason "..." --until-unit FE-03
```

## 5. O que você não faz

A cerca barra estas coisas antes de elas acontecerem. Se você for barrado, **a saída não é
insistir nem contornar** — é uma das três acima.

- **Publicar ou fundir**, se você não é a sessão de integração. Commite na sua cópia e pare;
  quem publica é o estágio de integração, adiante nesta mesma esteira.
- **Publicar com força, espelho ou remoção de branch.** Nem a integração faz isso.
- **Elevar privilégio, publicar pacote, baixar e executar script da rede.**
- **Apagar recursivamente fora da sua cópia de trabalho.**
- **Ler ou escrever a credencial pessoal de alguém.** A credencial que você pode usar é a do
  ambiente fechado do projeto, feita para ser descartável.
- **Rodar git fora da sua cópia de trabalho.** Em repositório aninhado, isso mexe no
  repositório errado.

## 6. Precisa ver o produto rodando?

Não use credencial de gente de verdade e não aponte para base de homologação. Existe um
ambiente fechado para isso — chame a skill que o constrói (`esteira-sandbox`). Se o
ambiente subir, **derrubá-lo é obrigação sua**: o encerramento declarado na esteira roda
sozinho, mas só se estiver declarado. Ambiente que ninguém derruba já prendeu 8,8 GB por
uma noite inteira e travou a esteira toda.
