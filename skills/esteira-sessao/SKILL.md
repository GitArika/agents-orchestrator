---
name: esteira-sessao
description: Use quando esta sessão foi lançada por uma esteira e recebeu uma ordem de serviço — o contrato de trabalho do papel único auto-contido: ler o cartão inteiro, implementar, revisar o próprio trabalho, abrir o PR, e terminar por exatamente um dos dois caminhos previstos. Use também quando alguém pedir para executar uma unidade da esteira à mão, quando você estiver numa cópia de trabalho da esteira e não souber como encerrar o que fez, ou quando um comando seu for barrado pela cerca e você precisar saber o que fazer em vez de insistir.
---

# O contrato da sessão de papel único

Você foi lançada por uma esteira. Um papel só, um ciclo inteiro: ler o requisito,
implementar, revisar o próprio trabalho, abrir o PR, atualizar o cartão. **Não há segunda
sessão atrás de você** — o que você não verificar, ninguém verifica antes de uma pessoa
olhar o PR.

## 1. Marque o cartão e leia a tarefa inteira — antes de qualquer outra coisa

```bash
orq-clickup set-status <id da tarefa> "em progresso"
orq-clickup show <id da tarefa>
```

O status muda SEM comentário — o Telegram já avisa que a unidade começou. `show` imprime a
descrição **e** todos os comentários, do mais antigo ao mais recente. Os comentários não são
conversa paralela: é onde mora

- divergência entre a descrição e o código real, registrada por quem veio antes;
- ambiguidade que uma sessão anterior encontrou e deliberadamente **não** resolveu sozinha;
- um pedido de mudança de uma revisão anterior — se esta unidade já teve PR devolvido, é o
  seu escopo agora, com prioridade sobre o resto do cartão;
- instrução escrita por uma pessoa no meio do caminho.

Tratar a descrição como o todo é o erro mais caro desta esteira: você refaz uma decisão que
já foi tomada, ou repete um engano que já foi diagnosticado.

## 2. Prepare o ambiente com o que o `CLAUDE.md`/`AGENTS.md` do projeto manda

A cópia de trabalho nasce **sem dependências instaladas** e sem os arquivos de ambiente que
o git ignora. Quem diz como deixar isto pronto é o `CLAUDE.md`/`AGENTS.md` do **próprio**
projeto — não uma cópia mantida à parte, que diverge do comando real e falha pelo motivo
errado. Se o repositório não tiver nenhum dos dois: pare com `orq hold`. Não é "sem
portão" — é um projeto sem guia, e inventar um comando é pior que admitir a lacuna.

## 3. Implemente — escopo é o do cartão

Defeito fora de escopo vira comentário no cartão (`orq-clickup comment`), não conserto.
Escopo alargado é motivo de devolução, e com razão: quem revisa precisa julgar uma coisa,
não três. Ambiguidade genuína no critério: pare e pergunte — não decida sozinho por um lado.

## 4. Revise o próprio trabalho — não há segunda leitura

Para CADA critério de aceite do cartão: atendido, não atendido, ou não verificável — com
evidência (arquivo e linha, ou a saída de um comando). Critério sem evidência **não** está
atendido. O caminho para isso é travar (`orq hold`), nunca afirmar.

## 5. Rode a verificação que o `CLAUDE.md` manda

Tipo, lint, teste — o que o projeto declarar. Cole a saída no corpo do PR.

## 6. Commit, publique, abra o PR — e NÃO funda

```bash
git add -A && git commit -m "<tipo(escopo): assunto>"
git push -u origin <seu branch>
gh pr create --base <base da esteira> --repo <owner>/<repo> \
    --title "<tipo(escopo): assunto>" --body "<...>"
```

O corpo do PR carrega: os critérios de aceite com a evidência do passo 4, a saída da
verificação do passo 5, e o que ficou fora de escopo e por quê.

**Você não funde.** `gh pr merge` é barrado pela cerca, sem exceção — quem decide fundir é
uma pessoa, olhando o diff.

Se a cerca barrar o `git push`: a saída não é contornar nem tentar outro jeito — pare com
`orq hold` explicando que a publicação foi barrada. Ordem que a cerca proíbe não é ordem.

## 7. Encerre — por um destes dois caminhos, sempre

```bash
orq advance <unidade> --pr <número ou URL do PR>   # PR aberto → 'revisão'
orq hold    <unidade> --motivo "<o que exatamente trava>"   # → 'bloqueado'
```

`advance` só depois do PR aberto — o comando recusa se o PR não existir de verdade no
`github_repo` declarado. `hold` é para o que só uma pessoa resolve: credencial que falta,
decisão de produto, ambiguidade que não dá para resolver sozinho. O motivo precisa dizer o
que trava, com pelo menos vinte caracteres — é validado. "Não consegui" não é motivo.

**Não existe um terceiro caminho de "reprovar".** Quem reprova agora é o gate humano, no PR
— o caminho de volta é a esteira relançar você com os comentários da revisão, não um comando
seu.

**Encerrar sem nenhum dos dois deixa a unidade num status de trabalho, e a esteira lê isso
como sessão morta.** A unidade some do radar até o laço recolher, contando uma falta. Isto
já aconteceu; é a razão de este parágrafo existir.

## 8. Só depois, atualize o cartão — os dois lados do espelho

Se você abriu PR:

```bash
orq-clickup set-status <id da tarefa> "revisão"
orq-clickup comment <id da tarefa> "<URL do PR, os critérios de aceite com a
    evidência do passo 4, e a saída da verificação do passo 5>"
```

Se você travou:

```bash
orq-clickup set-status <id da tarefa> "bloqueado"
orq-clickup comment <id da tarefa> "AGUARDANDO DECISÃO HUMANA: <o mesmo
    motivo que você passou a --motivo>"
```

**Nesta ordem, não na inversa:** o banco (passo 7) é a autoridade da esteira; o cartão é só o
espelho que uma pessoa lê. Se você morrer entre os dois passos, a divergência fica visível
no lugar onde alguém olha — o cartão —, e o rastro do banco permite reconstruir o que houve.

## O que você não faz

A cerca barra estas coisas antes de elas acontecerem. Se você for barrado, **a saída não é
insistir nem contornar** — é um dos dois caminhos do passo 7.

- **Fundir, sob qualquer forma.** `gh pr merge` é barrado sempre, mesmo no seu próprio
  branch. Quem funde é uma pessoa.
- **Publicar em qualquer lugar que não seja o seu próprio branch.** Publicar o seu branch é
  permitido; publicar a base, o branch de outra unidade, ou com força/espelho/remoção,
  nunca.
- **Abrir PR para uma base diferente da declarada na esteira.**
- **Elevar privilégio, publicar pacote, publicar release, baixar e executar script da rede.**
- **Apagar recursivamente fora da sua cópia de trabalho.**
- **Ler ou escrever a credencial pessoal de alguém, nem o banco da esteira.** A credencial
  que você pode usar é a do ambiente fechado do projeto, feita para ser descartável. O
  estado muda só pelos verbos (`orq advance`, `orq hold`).
- **Rodar git fora da sua cópia de trabalho.** Em repositório aninhado, isso mexe no
  repositório errado.

## Precisa ver o produto rodando?

Não use credencial de gente de verdade e não aponte para base de homologação. Existe um
ambiente fechado para isso — chame a skill que o constrói (`esteira-sandbox`). Se ele sobe
serviços via `docker-compose*.yml` na raiz da sua worktree, o encerramento é **automático**
quando a unidade sai de `em_progresso` — não precisa derrubar nada você mesma. Qualquer
outro processo que você tenha subido por fora disso (um servidor bare, sem Docker) não tem
reaper nenhum: **derrubá-lo antes de encerrar é obrigação sua**. Ambiente que ninguém
derruba já prendeu 8,8 GB por uma noite inteira e travou a esteira toda.
