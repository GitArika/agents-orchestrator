# Instalação

```bash
git clone <endereço deste repositório> ~/orquestrador
cd ~/orquestrador
./instalar.sh
```

`./instalar.sh --simular` mostra tudo o que ele faria e **não escreve nada**. Rode isso
primeiro se quiser conferir antes.

Rodar de novo é seguro — é assim que se atualiza.

## O que cada passo toca fora do repositório

**1. Procura segredo dentro do repositório.** Se achar, para. Um repositório que vai para o
GitHub interno não pode ter token dentro, e a hora de descobrir é antes de instalar.

**2. Confere os pré-requisitos chamando cada um.** Git, Python, Node (20 ou mais novo),
tmux e Docker (estes dois opcionais, com aviso). E pergunta ao agente de verdade — não
consulta o estado dele, pergunta. Um agente que responde "estou logado" e não responde a um
prompt faz toda sessão morrer dois segundos depois de nascer.

**3. Liga os executáveis em `~/.local/bin`.** Por atalho, nunca copiando — assim
`git pull` atualiza tudo de uma vez e nada envelhece numa cópia esquecida.
Use `--bin-dir OUTRO` se preferir outro lugar.

**4. Liga as skills em `~/.claude/skills`.** Mesmo motivo. `--sem-skills` pula.

**5. Cria `~/.config/orquestrador/credenciais.env`** com permissão restrita, se não existir.
Se já existir, não toca — só corrige a permissão se estiver frouxa.

**6. Confere a cerca de permissões** e roda a bateria de casos dela. Se a bateria falhar,
para: cerca com defeito deixa tudo passar e dá confiança falsa.

O instalador **não** consulta `git`, gerenciador de pacotes ou comando de teste do seu
projeto — decisão de 22/09/2026: o orquestrador deixou de declarar portões. Quem sabe como
preparar e verificar cada projeto é o próprio `CLAUDE.md`/`AGENTS.md` dele, lido pela sessão
no momento em que ela trabalha, nunca uma cópia mantida à parte.

## As credenciais

Duas, no mesmo arquivo: `~/.config/orquestrador/credenciais.env` (permissão 600).

### ClickUp

No ClickUp: **Settings → Apps → API Token**.

```
CLICKUP_API_KEY=pk_...
```

**Ele é pessoal.** Tudo que a esteira escrever — comentário, mudança de status — aparece
como escrito por você. Não use o token de outra pessoa. Confira a qualquer momento com:

```bash
orq-clickup whoami
```

### Telegram

Fale com `@BotFather` no Telegram (`/newbot`) para criar o bot e pegar o token. Depois mande
qualquer mensagem para o bot (ou adicione-o a um grupo) e leia
`https://api.telegram.org/bot<TOKEN>/getUpdates` para achar o `TELEGRAM_CHAT_ID` — o campo
`"chat":{"id": ...}` da resposta.

```
TELEGRAM_BOT_TOKEN=123456789:AAExemploDoTokenAqui
TELEGRAM_CHAT_ID=-1001234567890
```

Com as duas linhas preenchidas, o Telegram passa a ser o destino **padrão** de todo aviso do
orquestrador — PR aberto, unidade bloqueada, falha operacional. Prove que chegou:

```bash
orq-avisar --testar
```

### GitHub

O vigia de PR (dentro do laço, a cada 60s) e o `advance` que confere se o PR existe usam o
`gh` já autenticado na máquina — não há credencial própria do orquestrador para o GitHub.

```bash
gh auth status
```

`orq doctor` prova isto por chamada real; não adianta seguir sem ele, porque toda unidade
que chega a `revisão` depende do vigia para sair de lá.

## Declarar uma esteira

De dentro do repositório do projeto:

```bash
orq init --repo . --base main --worktrees ~/worktrees-do-projeto \
          --lista <id da lista> --github <owner>/<repo>
```

Cria o banco em `~/.config/orquestrador/esteiras/<nome>.db` — um arquivo por esteira, fora
do repositório do projeto. `--worktrees` também tem de ficar fora dele: worktree dentro do
repositório pai faz o `git status` dele listar milhares de arquivos não rastreados.

```bash
orq validate      # recusa uma esteira incoerente, sem escrever nada
orq doctor        # prova cada peça por chamada real
```

`orq validate` (que `orq doctor` também chama) exige que o repositório tenha `CLAUDE.md` ou
`AGENTS.md` na raiz — é de lá que o agente tira os portões agora. Projeto sem nenhum dos
dois nunca teria portão nenhum; a recusa antecipa isso em vez de deixar uma sessão descobrir
sozinha, no meio do trabalho.

## Quando algo falha

**"o agente não respondeu".** Rode `claude` uma vez e faça login. Não adianta seguir: cada
sessão morreria logo depois de nascer, e o quadro ficaria marcado como se alguém estivesse
trabalhando.

**"CLAUDE_CODE_OAUTH_TOKEN está no ambiente".** Tire essa variável do perfil do seu shell.
Ela vence o login interativo, desliga o acompanhamento remoto e rebaixa o modelo do seu
plano — tudo isso em silêncio.

**"já existe outra instalação na sua PATH".** É proteção. Aquela instalação pode estar
governando uma esteira **agora**, e trocar o caminho por baixo de sessões vivas é a forma
mais rápida de perder trabalho em voo. Confira que não há sessão viva (`orq status`) e só
então repita com `--substituir-instalacao`.

**"`~/.local/bin` não está na sua PATH".** Acrescente ao seu perfil:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Isto importa mais do que parece: as sessões chamam `orq advance`/`orq hold` por conta
própria ao terminar. Sem o comando na PATH, elas não conseguem se despedir, e a unidade
fica sem sessão viva até o laço recolher e contar falta.

## Atualizar

```bash
cd ~/orquestrador
git pull
./instalar.sh
```

Como tudo é atalho, o `git pull` já atualiza os executáveis e as skills. O instalador só
reconfere o que mudou.

## Não há migração do modelo antigo

Se você usava o modelo de quatro estágios (`pipeline.toml`, dez status), **não existe
caminho automático de compatibilidade** — foi decisão explícita de 21/09/2026: sem esteira
viva para migrar, começar limpo é mais barato do que carregar um conversor que ninguém mais
usa depois da primeira semana.

1. Confira que não há sessão viva da esteira antiga (`orq status`, se você ainda tiver o
   binário antigo na PATH) antes de substituir a instalação.
2. Declare a esteira de novo com `orq init` e `orq task add`/`orq dep add` — as unidades e
   o grafo não são importados do `pipeline.toml` antigo, que foi removido.
3. Rastro já coletado continua legível: `orq-medir coletar` lê os dois formatos sem
   misturar as contas, e o histórico da corrida antiga não some.
