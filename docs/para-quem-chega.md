# Para quem chega num projeto que já usa isto

Você entrou num time onde parte das tarefas é executada por sessões de IA governadas. Este
documento é para você entender o que está acontecendo e o que se espera de você.

## O que é uma sessão

Uma sessão é uma execução de IA com **um papel só, para uma unidade só**: lê o cartão,
implementa, revisa o próprio trabalho, abre um PR, atualiza o cartão. Não é um assistente
rodando o dia inteiro: é um turno com começo, meio e fim — e não há uma segunda sessão atrás
dela conferindo o que ela fez. O que ela não verificar, ninguém verifica antes de uma pessoa
olhar o PR.

## O que é uma cópia de trabalho (worktree)

Cada unidade ganha uma cópia isolada do repositório, num branch próprio. Duas sessões nunca
mexem nos mesmos arquivos ao mesmo tempo, porque cada uma está no seu próprio diretório.

Elas ficam **fora** da pasta do projeto, de propósito — dentro, o `git status` do projeto
passaria a listar milhares de arquivos que não são seus. A cópia **sobrevive** enquanto a
unidade está em revisão — se o PR voltar com pedido de mudança, a mesma sessão é relançada
nela — e só é removida quando a unidade chega a `pronto` ou `bloqueado`.

## O ciclo de ponta a ponta

Uma unidade atravessa até cinco status, e **uma única sessão** cuida dela do início até abrir
o PR:

1. **backlog** — declarada, esperando dependência ou vaga.
2. **em_progresso** — uma sessão nasceu: leu o cartão inteiro (descrição e comentários),
   preparou o ambiente seguindo o `CLAUDE.md`/`AGENTS.md` do projeto, implementou dentro do
   escopo do cartão, revisou o próprio trabalho critério por critério, rodou a verificação
   que o projeto declara, e abriu um PR.
3. **revisão** — o PR está aberto. **Aqui a esteira para e espera você.** Um vigia consulta
   o GitHub a cada 60 segundos, mas ele só reage ao que você decidir: aprovar e fundir,
   pedir mudanças, ou fechar sem fundir.
   - Fundiu → a unidade vai para **pronto**, e quem dependia dela é liberado.
   - `CHANGES_REQUESTED` → a mesma sessão é relançada com os seus comentários, a unidade
     volta para `em_progresso`. Na terceira devolução, ela para e vai para `bloqueado` — o
     defeito provavelmente está no requisito, não na implementação.
   - Fechado sem fundir → **bloqueado**.
4. **pronto** — estado terminal. A cópia de trabalho é removida, os artefatos ficam
   arquivados.
5. **bloqueado** — parou por decisão humana. Depois de resolver, `orq release` devolve para
   `backlog`.

Não existem mais sessão de especificação, de revisão ou de integração separadas — e nenhuma
sessão funde. Quem funde é sempre uma pessoa, olhando o diff no GitHub.

## O que é uma ordem de serviço (briefing)

O texto que a sessão recebe ao nascer: a unidade, o cartão, a worktree, o branch, e os oito
passos do papel único (ler, preparar, implementar, revisar, verificar, publicar e abrir PR,
encerrar, atualizar o cartão). Ele é montado a partir do cartão do ClickUp e do banco da
esteira — não existe mais um arquivo de configuração declarando estágios.

## O que se espera de você

**Escrever bons cartões.** A descrição do cartão vira a ordem de serviço. Descrição vaga
vira trabalho vago — e você só descobre quando abre o PR.

**Revisar o PR de verdade.** Não há mais uma sessão de revisão fazendo essa primeira
passada. A única barreira real entre o que o agente escreveu e a base é você olhando o diff.

**Responder quando a esteira te chamar.** Quando uma unidade vai para **bloqueado**, ela
está esperando uma pessoa. O motivo está no comentário do cartão e em `orq show <unidade>`.
Enquanto ninguém responde, aquela unidade e tudo que depende dela ficam parados.

**Fundir e fechar o cartão.** A esteira nunca faz nenhuma das duas por conta própria.

## Como conferir o que uma sessão fez

```bash
orq show <unidade>              # status, dependências, PR, eventos
orq-clickup show <id da tarefa> # descrição e todos os comentários
orq log <unidade> -f            # o que a sessão está fazendo, ao vivo
git log --oneline <branch da unidade>
```

O corpo do PR carrega os critérios de aceite com a evidência de cada um (arquivo e linha, ou
saída de comando) e a saída da verificação que o `CLAUDE.md` do projeto pede. Critério sem
evidência não está atendido — se um PR afirma algo sem provar, isso é um defeito do próprio
processo, e vale dizer.

## O que a sessão não pode fazer

Existe uma cerca. Ela barra, antes de acontecer: fundir (em qualquer forma), publicar fora do
próprio branch, publicar com força ou apagar branch, elevar privilégio, publicar pacote,
baixar e executar script da internet, apagar coisas fora da própria cópia de trabalho, e ler
credencial de gente de verdade.

Se você vir uma sessão dizendo que foi barrada, foi isso — e o comportamento certo dela é
parar e explicar (`orq hold`), nunca contornar.

## Uma coisa que costuma assustar no começo

As sessões rodam com permissão automática: elas executam sem pedir a cada passo. Isso é o que
permite a esteira andar sozinha. O que as contém é a combinação de três coisas: a cópia
isolada, a cerca, e o fato de que **elas não decidem nada de produto nem fundem nada** — quem
declara unidade, aprova o PR e fecha cartão é gente.

Se algo parecer errado, você pode parar tudo:

```bash
tmux kill-session -t orq-loop-<esteira>   # para de despachar
orq stop <unidade>                        # encerra uma sessão específica
```
