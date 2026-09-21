---
name: esteira-diagnosticar
description: Use quando a esteira não está fazendo o que deveria — nada é despachado, a sessão morre logo depois de nascer, o laço parou sozinho no meio do trabalho, o vigia de PR não avança nada, o ClickUp diz que alguém está trabalhando e não há ninguém, a máquina está arrastando, o acompanhamento remoto sumiu, o Telegram não chega, ou a escrita no ClickUp saiu com o nome de outra pessoa. Use também para caçar processo abandonado comendo memória, conferir o que limita o host, e antes de concluir que o problema é do projeto e não da esteira.
---

# Diagnosticar a esteira

Cada sintoma abaixo já aconteceu. A causa não é hipótese: é o que se provou verdadeiro.
**Confirme com o comando antes de agir** — a metade dos enganos aqui vem de tratar o
sintoma parecido.

## Comece por aqui

```bash
orq doctor      # prova cada dependência por chamada real
orq board       # o quadro: backlog, em_progresso, revisão, pronto, bloqueado
orq status      # o que está vivo e o que espera uma pessoa
orq host        # o que limita esta máquina agora
```

## Autenticação e sessão

**A sessão nasce e morre em dois segundos. O cartão marca "em progresso" e nada acontece.**
O token do agente está inválido. Viva para o tmux, morta para o trabalho.
`claude -p "responda apenas: ok"` — se não responder, é isto.
Nunca diagnostique por `claude auth status`: ele responde que está logado só por existir
uma variável de ambiente, e foi exatamente assim que um pré-voo ficou verde enquanto toda
sessão morria.

**"Remote Control disabled by your organization's policy".**
Quase sempre é mentira: é o mesmo 401 disfarçado. Sem autenticar, o cliente não carrega a
política remota e cai no padrão desligado. Com token válido, conecta normalmente.

**O modelo está mais fraco do que devia, e a sessão não aparece no celular.**
`CLAUDE_CODE_OAUTH_TOKEN` está no ambiente. Essa variável vence o login interativo, desliga
o acompanhamento remoto e rebaixa o modelo do plano.
`env | grep CLAUDE_CODE_OAUTH_TOKEN`. Dentro da sessão, `/status` deve dizer
`Login method: Claude Max account` — se disser `Auth token: CLAUDE_CODE_OAUTH_TOKEN`, é isto.

**A sessão trava antes de começar, sem produzir log.**
Toda cópia de trabalho é um caminho novo, e caminho novo dispara o diálogo de confiança do
Claude Code — que trava uma sessão desacoplada antes de ela começar. A esteira **herda** a
confiança do repositório base; se o base não for confiável, ela recusa em vez de decidir por
você. Abra o repositório base uma vez e aceite.

## Esteira e laço

**Uma unidade sumiu do radar, parada em `em_progresso`.**
A sessão terminou sem `advance` nem `hold`. `orq board` mostra as marcas de qualidade do
dado; ela volta sozinha a `backlog` (com falta contada) quando o laço ou `orq tick`
recolherem. Não é preciso um comando manual — se estiver com pressa, rode `orq tick`.

**O laço encerrou sozinho com sessões vivas.**
Contagem de ociosidade que não olhava se havia sessão viva: uma revisão longa gerava dezenas
de ciclos "sem mudança" e o laço desistia. Releia a tela da sessão `tmux` do laço, ou o
último evento `laco_parou`/`esteira_concluida` no banco — sempre registra o motivo.

**Foi despachada e não achou o código de que dependia.**
Com um papel só, dependência **sempre** é de código: a cópia de trabalho nasce do branch de
publicação, e o código de que ela depende só existe ali quando a dependência chegou a
`pronto` (fundida). `orq show <unidade>` mostra as dependências e o status de cada uma.

**Uma unidade em `revisão` está lá há muito tempo, e o vigia não faz nada.**
Confira se o laço está rodando (`ps`/`tmux ls`) e se `gh auth status` responde — o vigia só
avança quando o laço está de pé E o `gh` autentica. `orq doctor` prova as duas coisas.

**Nada é despachado, mas há unidades prontas em `backlog`.**
`orq capacity`. O teto pode estar em zero por memória, processador ou carga — o orçamento é
um só agora, não mais por estágio.

## Host e memória

**A máquina arrasta e o medidor mostra memória de sobra.**
Em Linux com systemd, o que sufoca é a **fatia do usuário**, não a máquina. Já houve fatia
em 12,7 GB de 18 com o swap dela cheio e mais de um milhão de freadas por memória, enquanto
o medidor da máquina anunciava 16 GB livres. `orq host` lê o número certo.
Lembre também que **containers rodam fora da fatia**: eles são filhos do serviço do Docker,
que é root. Conte-os à parte.

**Memória presa e ninguém sabe de quem.**
Ambiente de teste que ninguém derrubou. O encerramento é fixo agora — busca
`docker-compose*.yml`/`compose*.yml` na raiz da worktree e derruba sempre que a unidade sai
de trabalho. Se o ambiente não usa Docker Compose, ele não tem reaper nenhum: já foram 27
pilhas, 147 processos, 8,8 GB, uma noite inteira, antes desse mecanismo existir.

```bash
orq host --check
ps -eo pid,ppid,etimes,args --no-headers | awk '$2==1' | grep -E 'pnpm|node|vite|nest'
```

**Um comando de encerrar derrubou o próprio terminal.**
`kill -- -PID` num número que não lidera o próprio grupo. Em shell não interativo, `&` não
cria grupo novo. Confira antes: `ps -o pgid= -p <PID>` — só mate o grupo se o resultado for
igual ao próprio número.

## Telegram e ClickUp

**Nenhum aviso chega, e a esteira parece travada sem motivo.**
Credencial do Telegram ausente ou inválida. `orq-avisar --testar` manda de verdade e diz se
falhou — ao contrário do resto do avisador, que nunca lança exceção para não derrubar quem
chamou.

**A escrita saiu com o nome de outra pessoa.**
A escrita não saiu pelo cliente com o token pessoal. Aprovação atribuída a quem não aprovou
é falsificação de registro, ainda que involuntária. **Antes de qualquer escrita:**
`orq-clickup whoami`.

**A escrita responde 404 numa lista que a leitura encontra.**
Id de lista já apagada, devolvido por rota de navegação. Resolva pelo nome:
`orq-clickup find-list "<trecho>"`.

**Padronizei os status e a lista continua igual, mas a API respondeu sucesso.**
A lista **herda** os status da pasta ou do espaço. Sem `--substituir`, o PUT é aceito e
ignorado. `orq-clickup list <id> --json` mostra `override_statuses`.
Lição maior: a API responde sucesso sem ter feito nada — sempre releia depois de escrever.

**Apontamento de hora responde 403.**
Descrição e etiqueta em apontamento são recurso pago. Envie só `{tid, start, duration}`.

## Ferramentas do projeto

**O preparo da cópia de trabalho falha instalando dependências.**
Confira a versão do gerenciador de pacotes **antes** de acusar o projeto. Versões novas
recusam lockfile com dependência sem hash de integridade, e o erro parece do projeto.

**Um comando meu foi barrado e eu não entendo por quê.**
A cerca barrou. Ela diz o motivo e o que fazer. Ela julga pelo **branch**, não mais por
estágio: publicar o seu branch passa; publicar a base, fundir, ou publicar o branch de outra
unidade, nunca. Não contorne — a saída é `orq advance` ou `orq hold`.

**`orq doctor` fica vermelho em "declaração coerente (orq validate)".**
Rode `orq validate` sozinho para ver a lista completa de problemas — falta `CLAUDE.md`/
`AGENTS.md` na raiz, `worktree_root` dentro do repositório, `github_repo` não declarado, ou
um ciclo de dependência entre unidades são as causas mais comuns.
