# orquestrador

Transforma uma lista do ClickUp numa esteira que anda sozinha. Cada tarefa vira uma sessão
de IA auto-contida: ela lê o cartão, implementa numa cópia isolada do repositório, revisa o
próprio trabalho, abre um PR — e para aí. Quem funde é uma pessoa, olhando o diff.

Você continua sendo quem decide. A esteira é quem lembra, empurra e presta contas.

## O problema que isto resolve

Tarefa boa parada esperando alguém ter tempo. Trabalho de IA sem rastro — ninguém sabe o
que foi feito, por quem, com base em quê. Sessão que some no meio e deixa a tarefa num
limbo. Duas sessões mexendo no mesmo arquivo ao mesmo tempo. E, quando algo trava, ninguém
descobre até perguntar.

## Os primeiros dez minutos

```bash
git clone <endereço deste repositório> ~/orquestrador
cd ~/orquestrador
./instalar.sh                    # guiado; --simular mostra tudo sem escrever nada

cd <o seu projeto>
orq init --repo . --base main --worktrees ~/worktrees-do-projeto \
          --lista <id da sua lista no ClickUp> --github <owner>/<repo>
orq task add FE-01 --clickup <id da tarefa> --titulo "..."   # declara pelo menos uma unidade
orq doctor                       # prova cada peça por chamada real
orq board                        # o quadro

orq-medir coletar                # o que a esteira já produziu
orq-medir servir                 # o painel, no endereço local
```

`orq init` **não lê nada do projeto por você** — decisão de 22/09/2026: setup, verificação e
encerramento de ambiente deixaram de ser configuração da esteira e viraram responsabilidade
do agente, seguindo o `CLAUDE.md`/`AGENTS.md` que o projeto já declara. `orq init` só cria o
banco; `orq validate` (e `orq doctor`, que o chama) recusa uma esteira incoerente antes de
qualquer despacho.

## O que tem aqui

| Pasta | O que é |
| --- | --- |
| `bin/` | Os cinco executáveis: o motor (`orq`), o cliente do ClickUp, o avisador do Telegram, o vigia de memória e o medidor |
| `skills/` | Oito habilidades que um agente aciona — operar, diagnosticar, construir ambiente, instalar |
| `modelos/` | Exemplo de credenciais e o modelo do painel de medição |
| `hooks/` | A cerca de permissões e o aviso |
| `docs/` | Esta documentação |
| `testes/` | O que se prova sozinho |

## A documentação

| Documento | Para quê |
| --- | --- |
| [Instalação](docs/instalacao.md) | Passo a passo, o que cada passo toca, e o que fazer quando falha |
| [Organização no ClickUp](docs/clickup.md) | Os cinco status, quem manda em quê, como escrever sem falsificar autoria |
| [Operação no dia a dia](docs/operacao.md) | Ler o quadro, despachar, reconhecer que a esteira espera **você** |
| [Para quem chega](docs/para-quem-chega.md) | Entrou num projeto que já usa isto? Comece por aqui |
| [Segurança](docs/seguranca.md) | A cerca, o que ela cobre e o que ela não cobre |
| [Host Linux](docs/host-linux.md) | Rodar sozinho num servidor |
| [Medição](docs/medicao.md) | O que a esteira produziu: sessões, retrabalho, espera humana, tokens e código |
| **[Aprendizados](docs/aprendizados.md)** | **O que já custou tempo descobrir** |

**Comece pelos aprendizados se quiser saber se isto vale a pena.** É a parte que não se
inventa: cada item é um problema que já aconteceu, com o número exato, o comando que
confirma e o que foi feito para não repetir. Ferramenta se escreve de novo; essas
descobertas, não.

## O modelo: um papel só, cinco status, gate humano

Até 21/09/2026 a esteira tinha quatro estágios — especificação, implementação, revisão,
integração — cada um uma sessão diferente, dez status no ClickUp, e um arquivo
`pipeline.toml` versionado descrevendo o grafo. Isso mudou por inteiro.

**Hoje é um papel só.** Uma sessão lê o cartão inteiro (descrição e comentários), implementa,
revisa o próprio trabalho contra os critérios de aceite, roda a verificação que o
`CLAUDE.md`/`AGENTS.md` do projeto manda, e abre um PR. Ela nunca funde — a cerca barra
`gh pr merge` sem exceção.

**O estado vive em SQLite**, um banco por esteira (`~/.config/orquestrador/esteiras/<nome>.db`),
não mais num arquivo TOML no repositório do projeto. Cinco status, os mesmos dos dois
lados (banco e ClickUp): `backlog` → `em_progresso` → `revisão` → `pronto`, com `bloqueado`
alcançável de quase qualquer um deles.

**Quem revisa é uma pessoa, no PR.** Um vigia dentro do laço autônomo consulta o `gh` a cada
60 segundos: PR fundido avança a unidade para `pronto` e libera quem dependia dela;
`CHANGES_REQUESTED` relança a mesma sessão com os comentários da revisão; PR fechado sem
merge bloqueia. Nenhum agente revisa o trabalho de outro agente — o que substituiu a revisão
independente foi o humano olhando o diff, e a taxa de devolução é o termômetro disso.

**O Telegram é o canal padrão de aviso.** PR aberto, unidade bloqueada e falha operacional
chegam lá — exceto sessão pedindo decisão dentro do app, que já chega por outro caminho.

O desenho completo, com as decisões e o porquê de cada uma, está em
[`docs/specs/orquestrador-agil/index.md`](docs/specs/orquestrador-agil/index.md).

## O que já se sabe

Cada linha abaixo custou tempo. Elas não são preferências de estilo: são consertos de
coisas que quebraram, e a história completa de cada uma está nos
[Aprendizados](docs/aprendizados.md).

- **A cerca é um gancho, não uma lista de permissões.** A lista foi tentada primeiro e
  **não funcionou**: uma negação injetada pela esteira perdeu para uma permissão idêntica
  que a pessoa já tinha. O gancho vê o comando inteiro e não é anulável por ninguém.
- **Dependência entre unidades mora no banco, não no ClickUp.** Dependência é decisão
  técnica e precisa ser revisada com o código; campo de ferramenta de gestão muda sozinho.
- **Tarefa que está no ClickUp e não foi declarada nunca é executada.** Esteira que roda o
  que aparece na lista é esteira que qualquer um dispara sem querer.
- **Atribuir trabalho pelo intervalo `base..branch` mente.** Com a base local atrasada, o
  intervalo devolve o trabalho de todas as unidades de uma vez. A atribuição correta sai do
  **merge**, que diz de qual branch veio o que entrou.
- **O status `bloqueado` não é enfeite.** Sem ele, o quadro mostra `em_progresso` e todo
  mundo acha que uma sessão está trabalhando, quando na verdade a esteira espera **você**.
- **Confira a autoria antes de escrever no quadro.** Uma aprovação já foi publicada assinada
  por outra pessoa, porque a escrita saiu por um caminho autenticado com a sessão de outro.
  Aprovação atribuída a quem não aprovou é falsificação de registro, mesmo sem má intenção.
- **Orçamento de memória se corrige por medida, não por palpite.** Um palpite sete vezes
  acima do real fez uma máquina admitir uma sessão por vez quando cabiam oito.
- **Encerramento do ambiente não é opcional, e não é mais configurável.** Ele é fixo: busca
  `docker-compose*.yml` na raiz da worktree e derruba. Sem ele, cada sessão deixa serviço
  vivo para trás — já foram 27 pilhas segurando 8,8 GB.
- **Antes de assumir que falta um recurso, procure o mesmo fato num rastro que você já
  produz.** O tempo em cada status do ClickUp é pago; os comentários das tarefas dão a mesma
  linha do tempo de graça, e ainda dizem o que aconteceu e quem assinou.

## O que uma corrida real produziu

Números medidos pela própria ferramenta, numa esteira de front-end de 30 unidades —
**do modelo de QUATRO ESTÁGIOS, encerrado em 21/09/2026.** Não há ainda uma corrida
completa no modelo de papel único para comparar; quando houver, esta tabela ganha uma
segunda coluna.

| | |
| --- | --- |
| Sessões governadas | **249** |
| Terminaram avançando | **78,7%** (196) |
| Travaram chamando uma pessoa | 23 |
| Reprovadas na revisão | 18 |
| Morreram sem se despedir | 3 |
| Tempo de sessão medido | 141 h |
| Código integrado | +97.609 / −23.112 linhas em 157 commits |
| Tokens gerados | 19 milhões |

Mediana por etapa: especificação 18 min, revisão 15 min, integração 21 min e implementação
**36 min — com uma em cada dez passando de três horas**. É o único estágio em que estimar
pela média enganava; a distribuição inteira, sem separar por estágio, é a métrica que
substitui isso no modelo novo.

Como reproduzir na sua esteira: `orq-medir coletar && orq-medir resumo`.

## O que isto NÃO faz

- **Não é contenção contra código hostil.** A cerca reduz o raio de dano de um agente que
  erra. Repositório com dependência não confiável está fora do que ela protege.
- **Só fala com o ClickUp.** Outras ferramentas de gestão ficam de fora; a fronteira está
  isolada para que um dia isso seja trabalho, não reescrita.
- **Não decide por você.** Declarar unidade, aprovar o PR e fechar cartão continuam sendo
  humanos. Nenhum agente funde, em nenhuma circunstância.
- **A cobertura de testes é parcial, e o recorte é deliberado.** Tem bateria completa no
  motor de estado, no medidor, na cerca e no lançador — cerca com defeito deixa tudo passar
  e dá confiança falsa. O laço autônomo em si continua provado pelo pré-voo honesto e pela
  primeira esteira real no modelo novo, não por teste de ponta a ponta.
- **Não migra sua máquina sozinho.** Não existe caminho de compatibilidade com o modelo de
  quatro estágios: começa limpo. Está em [Instalação](docs/instalacao.md).
