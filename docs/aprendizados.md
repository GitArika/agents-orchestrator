# Aprendizados

Vinte coisas que custaram tempo descobrir. Cada uma no mesmo formato: o sintoma, o que
parecia ser, o que era, o comando que confirma, e como não repetir.

Não é lista de dicas. É o que já deu errado, com os números.

---

## 1. O pré-voo dizia que estava tudo bem e cada sessão morria em dois segundos

**O sintoma.** As sessões subiam, o quadro do ClickUp marcava "revisando", e nada
acontecia. Vistas de fora, as sessões estavam vivas: o tmux mostrava o processo.

**O que parecia ser.** Sessões travadas em algum passo demorado.

**O que era.** O token do agente estava inválido. Cada sessão morria em dois segundos com
`401 OAuth access token is invalid` — viva para o tmux, morta para o trabalho. O pré-voo
tinha dado verde porque perguntava `claude auth status`, que responde `loggedIn: true` só
por existir uma variável de ambiente.

**O comando que confirma.**

    claude -p "responda apenas: ok"

**Como não repetir.** Ferramenta que acredita em declaração é pior do que não ter
ferramenta: ela dá permissão para seguir e some do caminho quando o problema aparece. Todo
pré-voo aqui **chama de verdade** e mostra o que voltou.

---

## 2. Uma variável de ambiente rebaixava o modelo e desligava o acompanhamento remoto

**O sintoma.** As sessões pareciam mais fracas do que o normal, e nenhuma aparecia na lista
do celular.

**O que parecia ser.** Instabilidade do serviço.

**O que era.** `CLAUDE_CODE_OAUTH_TOKEN` no ambiente. Ela vence o login interativo guardado
na máquina e força o modo de chave de API, que **desliga o acompanhamento remoto** e
**rebaixa o modelo do plano**.

**O comando que confirma.** `env | grep CLAUDE_CODE_OAUTH_TOKEN`, e dentro da sessão
`/status`: o certo é `Login method: Claude Max account`; o errado é
`Auth token: CLAUDE_CODE_OAUTH_TOKEN`.

**Como não repetir.** Nunca ponha essa variável no perfil do shell de uma máquina que
hospeda a esteira. O pré-voo agora **para** quando a encontra.

---

## 3. "Remote Control desativado pela política da sua organização" era mentira

**O sintoma.** Exatamente essa mensagem, que parece definitiva e administrativa.

**O que parecia ser.** Uma política da empresa bloqueando o recurso.

**O que era.** O mesmo 401 do item 1, disfarçado. Sem autenticar, o cliente não carrega a
política remota e cai no padrão, que é desligado.

**O comando que confirma.** `claude -p "responda apenas: ok"`. Se falhar, é isto.

**Como não repetir.** Desconfie de mensagem que atribui a causa a outra pessoa. Antes de
abrir chamado, prove a autenticação.

---

## 4. Uma cópia de trabalho nova travava a sessão antes de ela começar

**O sintoma.** A sessão subia e não produzia log nenhum. Nada, nem erro.

**O que parecia ser.** Falha de lançamento.

**O que era.** Toda cópia de trabalho é um caminho novo no disco, e caminho novo dispara o
diálogo de confiança de pasta do Claude Code — que espera uma resposta que ninguém ia dar,
porque a sessão estava desacompanhada.

**O comando que confirma.** `orq doctor` — a linha da confiança do repositório base.

**Como não repetir.** A esteira **herda** a confiança do repositório base para cada cópia
nova. E se o base não for confiável, ela **recusa** em vez de decidir por você: conceder
confiança em nome de alguém não é papel de ferramenta.

---

## 5. Uma sessão que termina sem se despedir some do radar

**O sintoma.** Uma unidade parada num status de trabalho, sem ninguém trabalhando nela.

**O que parecia ser.** Sessão ainda rodando, devagar.

**O que era.** A sessão encerrou sem chamar nenhum dos três caminhos de saída. O status de
trabalho ficou marcado e o laço leu aquilo como sessão morta.

**O comando que confirma.** `orq board` — ela aparece como travada.

**Como não repetir.** Toda ordem de serviço termina com o mesmo bloco: concluí, reprovei ou
travei. E o laço recolhe automaticamente unidades em status de trabalho sem sessão viva.

---

## 6. O laço autônomo se matava no meio do próprio trabalho

**O sintoma.** A esteira parava sozinha com sessões vivas trabalhando. Quando uma delas
finalmente avançava a unidade, não havia ninguém para despachar o estágio seguinte.

**O que parecia ser.** Uma parada legítima por falta de trabalho.

**O que era.** A contagem de ociosidade tratava como ocioso todo ciclo "sem mudança",
mesmo havendo sessão viva. Uma revisão de trinta minutos gerava vinte ciclos assim, e o
laço desistia. Aconteceu duas vezes no mesmo dia.

**O comando que confirma.** `cat ~/.claude/orchestrator/state/notify.log` — o motivo da
parada fica registrado ali.

**Como não repetir.** Ocioso passou a significar "nada mudou **e** nada está vivo". Quando o
laço parar sozinho, o primeiro lugar a olhar é sempre esse registro.

---

## 7. Uma sessão foi despachada e não achou o código de que dependia

**O sintoma.** A unidade foi despachada normalmente, a sessão abriu, e não encontrou nada do
que precisava para trabalhar. Precisou ser bloqueada.

**O que parecia ser.** Erro na declaração da dependência.

**O que era.** A dependência estava declarada certo — mas com a regra genérica, que libera
o trabalho quando a dependência chega em "aguardando revisão". A cópia de trabalho nasce do
**branch de publicação**: enquanto a dependência não está **integrada**, o código dela não
existe naquela base. Uma sessão gasta, nada produzido — e o mesmo desfecho esperava outras
doze unidades.

**O comando que confirma.** No arquivo da esteira: `[pipeline.dependency]` precisa dizer
`after = "integrate"` quando a dependência é de código.

**Como não repetir.** Distinga dependência de **decisão** (basta a revisão) de dependência
de **código** (precisa da integração). E preserve o paralelismo com `from = "implement"`: a
especificação de B continua correndo enquanto A é implementada.

---

## 8. Um orçamento de memória inventado serializou a esteira inteira

**O sintoma.** A máquina admitia uma sessão de implementação por vez. O teto configurado de
oito nunca era alcançado.

**O que parecia ser.** Máquina pequena demais.

**O que era.** O orçamento de memória por sessão era um palpite: 2,5 a 3,0 GB. A medida real
das sessões vivas era 0,38 a 0,40 GB. **Sete vezes acima.**

**O comando que confirma.** `orq capacity` mostra o consumo real das sessões vivas.

**Como não repetir.** Corrija o orçamento **por medida**. Mas não desça até o número medido:
ele é só o processo do agente, e uma sessão de implementação também dispara instalação de
dependências, verificação de tipos e testes, que sobem em rajada. Medida do agente, mais
folga para os filhos.

---

## 9. A esteira nunca executa o que não foi declarado

**O sintoma.** Uma tarefa nova no ClickUp não era despachada.

**O que parecia ser.** Defeito.

**O que era.** Comportamento proposital. Tarefa que existe na lista e não está declarada no
arquivo da esteira aparece marcada como deriva e nunca é executada.

**O comando que confirma.** `orq board` — a linha de deriva.

**Como não repetir.** Isto não é para consertar. Declarar uma unidade é decisão humana,
revisada em pull request junto com o código que ela vai mexer. Uma esteira que executa o que
aparece na lista é uma esteira que qualquer pessoa dispara sem querer.

---

## 10. O que sufoca um servidor Linux é a fatia, não a máquina

**O sintoma.** A esteira arrastando. Sessões que levavam minutos passaram a levar dezenas de
minutos. O medidor da máquina mostrava 16 GB livres de 31.

**O que parecia ser.** Excesso de sessões, ou o agente ficando mais lento.

**O que era.** A esteira roda dentro de uma fatia de 18 GB. A fatia estava em **12,7 GB**,
com o **swap dela 100% cheio**, e o núcleo já havia freado os processos **1.104.943 vezes**
por excesso de memória. A memória livre da máquina era irrelevante.

**O comando que confirma.**

    orq host

**Como não repetir.** Em Linux com systemd, leia a fatia do usuário. E lembre que
**containers ficam fora dela**: rodam sob o serviço do Docker, que é root, então não são
contidos pelo teto — conte-os à parte.

---

## 11. O ambiente de teste que sobreviveu à noite

**O sintoma.** O mesmo do item anterior: a esteira arrastando com memória aparentemente
sobrando.

**O que parecia ser.** Consumo natural de várias sessões.

**O que era.** Presos na fatia: **27 ambientes de teste** da noite anterior — **147
processos**, **8,8 GB** de memória real — que ninguém derrubou. A ferramenta gravava o
endereço da aplicação num arquivo só, sobrescrito a cada subida; os processos da subida
anterior ficavam vivos sem ninguém que soubesse o número deles, e o comando de derrubar só
derrubava os containers. Uma única cópia de trabalho tinha acumulado nove.

Depois da limpeza: 4,9 GB e swap zerado.

**O comando que confirma.**

    orq host
    ps -eo pid,ppid,etimes,args --no-headers | awk '$2==1' | grep -E 'pnpm|node'

**Como não repetir.** Encerramento é **contrato**, não boa vontade: o bloco `teardown` roda
em todo caminho de saída da sessão, inclusive quando ela morre, e a varredura cobra o que
ficou de pé. Um registro **por cópia de trabalho**, nunca um só.

---

## 12. Registro único e sobrescrito apaga o rastro de quem ficou vivo

**O sintoma.** Ninguém conseguia dizer quais processos pertenciam a qual sessão.

**O que parecia ser.** Bagunça acumulada.

**O que era.** Um arquivo de registro só, sobrescrito a cada subida. A informação de quem
estava vivo era destruída pela subida seguinte — que é exatamente quando ela passaria a ser
necessária.

**O comando que confirma.** Compare o número de processos vivos com o número de registros.

**Como não repetir.** Um registro por cópia de trabalho. Vale também para **log**: log único
faz duas sessões simultâneas se sobrescreverem, e o diagnóstico aponta para o lugar errado.

---

## 13. Matar o grupo de processos derrubou o próprio terminal

**O sintoma.** No meio de um teste de encerramento, a sessão remota caiu e o script parou na
metade, sem limpar nada.

**O que parecia ser.** Queda de conexão.

**O que era.** `kill -- -PID` num número que **não liderava o próprio grupo**. Em shell não
interativo, `&` não cria grupo novo: o processo em segundo plano fica no mesmo grupo do
shell. Matar "o grupo dele" era matar o grupo de quem chamou.

**O comando que confirma.**

    ps -o pgid= -p <PID>     # só mate o grupo se isto for igual ao próprio PID

**Como não repetir.** Antes de matar um grupo, prove que o número registrado é o líder.
Quando não for, mate só o processo. É uma linha de código e evita derrubar quem chamou.

---

## 14. Num servidor, o aviso é silencioso

**O sintoma.** A esteira parecia travada sem motivo. Havia unidades esperando uma decisão
humana havia horas.

**O que parecia ser.** Esteira parada.

**O que era.** O aviso gravava em arquivo e tentava notificação de sistema. Num servidor sem
tela, a notificação não existe e o arquivo ninguém lê. A espera humana só se descobria
consultando o quadro à mão.

**O comando que confirma.** `orq status` — as linhas com ⚠.

**Como não repetir.** Configure um destino de verdade (`ORQ_AVISO_DESTINO`) em toda máquina
sem tela. O registro em arquivo continua acontecendo sempre, mas registro não é entrega.

---

## 15. A espera humana não aparecia no quadro

**O sintoma.** Quem abria o ClickUp via uma unidade em "revisando" e concluía que alguém
estava revisando. Não estava: ela esperava uma resposta.

**O que parecia ser.** Trabalho em curso.

**O que era.** O bloqueio vivia só no estado local da máquina e num comentário. O status
continuava sendo o do estágio.

**O comando que confirma.** `orq status` mostrava a espera; o quadro do ClickUp, não.

**Como não repetir.** Existe um status **parado**. A unidade vai para ele ao travar e volta
de onde saiu ao ser solta. Um quadro que não mostra a espera é um quadro que mente.

---

## 16. Uma aprovação foi publicada assinada por outra pessoa

**O sintoma.** Um registro de aprovação num cartão, com o nome de alguém que não aprovou
nada.

**O que parecia ser.** Engano de quem escreveu.

**O que era.** A escrita saiu por um servidor de integração cuja sessão autorizada naquela
máquina era de outra pessoa. Ninguém percebeu porque a operação foi bem-sucedida.

**O comando que confirma.**

    orq-clickup whoami

**Como não repetir.** Toda escrita sai pela linha de comando, com o token **pessoal**.
Aprovação atribuída a quem não aprovou é falsificação de registro, ainda que involuntária —
e é o tipo de erro que só aparece quando já está publicado.

---

## 17. A API respondeu sucesso e não fez nada

**O sintoma.** O provisionamento de status disse "9 status criados". A lista continuou com
os cinco de sempre.

**O que parecia ser.** Atraso de propagação.

**O que era.** A lista **herdava** os status da pasta. Sem ligar a substituição, o pedido é
aceito, responde 200, e é ignorado.

**O comando que confirma.**

    orq-clickup list <id> --json     # veja override_statuses

**Como não repetir.** Depois de escrever, **releia e compare**. Ferramenta que acredita na
resposta da API mente para quem confia nela. E quando a esteira vai ocupar a pasta inteira,
o certo é definir os status na pasta, não em cada lista.

---

## 18. A API devolve id de lista que já foi apagada

**O sintoma.** A leitura funcionava e a escrita respondia 404, sem explicar.

**O que parecia ser.** Problema de permissão.

**O que era.** Rotas de navegação devolvem listas já apagadas, com id e tudo.

**O comando que confirma.**

    orq-clickup find-list "<trecho do nome>"

**Como não repetir.** Resolva lista pelo nome quando houver qualquer dúvida, e não guarde id
copiado de navegação.

---

## 19. Apontamento de hora responde 403 por um campo a mais

**O sintoma.** 403 em toda tentativa de apontar hora.

**O que parecia ser.** Falta de permissão na conta.

**O que era.** Descrição e etiqueta em apontamento de hora são recurso pago. Enviá-los faz o
pedido inteiro ser recusado.

**O comando que confirma.** Envie só `{tid, start, duration}` e veja passar.

**Como não repetir.** Mande o mínimo. Campo opcional em API cobrada costuma ser opcional só
na documentação.

---

## 20. O erro parecia do projeto e era da ferramenta

**O sintoma.** O preparo de toda cópia de trabalho falhava instalando dependências. A
mensagem apontava para uma dependência do projeto.

**O que parecia ser.** Dependência quebrada no projeto.

**O que era.** A versão do gerenciador de pacotes. A partir de certa versão ele recusa
lockfile que contenha dependência sem hash de integridade — e o projeto tinha uma, vinda de
um arquivo direto do fornecedor.

**O comando que confirma.** Compare a versão do gerenciador com a que gerou o lockfile.

**Como não repetir.** Trave a versão na máquina que hospeda a esteira, e **olhe a versão da
ferramenta antes de acusar o projeto**. Vale também para o navegador de teste: ele fica
**fora** do repositório, porque acrescentá-lo às dependências quebraria a instalação
congelada de toda cópia de trabalho em voo.
