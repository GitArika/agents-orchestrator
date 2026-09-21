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

## O token do ClickUp

No ClickUp: **Settings → Apps → API Token**.

Ponha em `~/.config/orquestrador/credenciais.env`:

```
CLICKUP_API_KEY=pk_...
```

**Ele é pessoal.** Tudo que a esteira escrever — comentário, mudança de status, aprovação —
aparece como escrito por você. Não use o token de outra pessoa, e não deixe esse arquivo
entrar em repositório nenhum. Confira a qualquer momento com:

```bash
orq-clickup whoami
```

## Quando algo falha

**"o agente não respondeu".** Rode `claude` uma vez e faça login. Não adianta seguir: cada
sessão morreria logo depois de nascer, e o quadro ficaria marcado como se alguém estivesse
trabalhando.

**"CLAUDE_CODE_OAUTH_TOKEN está no ambiente".** Tire essa variável do perfil do seu shell.
Ela vence o login interativo, desliga o acompanhamento remoto e rebaixa o modelo do seu
plano — tudo isso em silêncio.

**"já existe outra instalação na sua PATH".** É proteção. Aquela instalação pode estar
governando uma esteira **agora**, e trocar o caminho por baixo de sessões vivas é a forma
mais rápida de perder trabalho em voo. Pare o laço, confira que não há sessão viva, e só
então repita com `--substituir-instalacao`.

**"`~/.local/bin` não está na sua PATH".** Acrescente ao seu perfil:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Isto importa mais do que parece: as sessões chamam `orq advance` por conta própria ao
terminar. Sem o comando na PATH, elas não conseguem se despedir, e a unidade fica num limbo.

## Atualizar

```bash
cd ~/orquestrador
git pull
./instalar.sh
```

Como tudo é atalho, o `git pull` já atualiza os executáveis e as skills. O instalador só
reconfere o que mudou.

## Já uso a versão anterior

A troca é um passo consciente. Nada acontece sozinho.

1. **Pare o laço** e confira que não há sessão viva:

   ```bash
   orq loop-stop
   orq status
   ```

   Se houver sessão viva, espere. Trocar o motor por baixo de uma sessão em trabalho é a
   forma mais fácil de perder o que ela fez.

2. **Instale**, aceitando substituir:

   ```bash
   cd ~/orquestrador && ./instalar.sh --substituir-instalacao
   ```

3. **Mova a credencial**, se ela estava dentro de algum repositório:

   ```bash
   ls -l ~/.config/orquestrador/credenciais.env    # tem de ser -rw-------
   ```

   Depois de confirmar que funciona (`orq-clickup whoami`), apague a cópia antiga.

4. **Aponte o arquivo da sua esteira** para o novo caminho de credencial:

   ```toml
   [clickup]
   token_file = "~/.config/orquestrador/credenciais.env"
   token_key  = "CLICKUP_API_KEY"
   ```

5. **Acrescente o encerramento**, se o seu projeto sobe algum serviço para trabalhar:

   ```toml
   [gates]
   teardown = ["..."]
   ```

   Sem isso, cada sessão deixa um ambiente vivo para trás. Já foram 27 numa noite,
   segurando 8,8 GB.

6. **Prove:**

   ```bash
   orq doctor
   ```
