# orquestrador

Transforma uma lista do ClickUp numa esteira que anda sozinha. Cada tarefa vira uma sessão
de IA governada: ela trabalha numa cópia isolada do repositório, passa pelos portões de
qualidade do projeto, e devolve a tarefa adiante — ou para e chama uma pessoa.

Você continua sendo quem decide. A esteira é quem lembra, empurra e presta contas.

## O problema que isto resolve

Tarefa boa parada esperando alguém ter tempo. Trabalho de IA sem rastro — ninguém sabe o
que foi feito, por quem, com base em quê. Sessão que some no meio e deixa a tarefa num
limbo. Três sessões mexendo no mesmo arquivo ao mesmo tempo. E, quando algo trava, ninguém
descobre até perguntar.

## Os primeiros dez minutos

```bash
git clone <endereço deste repositório> ~/orquestrador
cd ~/orquestrador
./instalar.sh                    # guiado; --simular mostra tudo sem escrever nada

cd <o seu projeto>
orq init --lista <id da sua lista no ClickUp>
orq doctor                       # prova cada peça por chamada real
orq board                        # o quadro

orq-medir coletar                # o que a esteira já produziu
orq-medir servir                 # o painel, no endereço local
```

O `orq init` **lê o seu projeto** antes de perguntar qualquer coisa: descobre o branch base,
o gerenciador de pacotes e os comandos de teste que ele já declara. O que sai é um arquivo
comentado, para você revisar — nada é decidido às escondidas.

## O que tem aqui

| Pasta | O que é |
| --- | --- |
| `bin/` | Os cinco executáveis: o motor, o cliente do ClickUp, o avisador, o vigia de memória e o medidor |
| `skills/` | Oito habilidades que um agente aciona — operar, diagnosticar, construir ambiente, instalar |
| `modelos/` | O modelo comentado da esteira e o exemplo de credenciais |
| `hooks/` | A cerca de permissões e o aviso |
| `docs/` | Esta documentação |
| `exemplos/` | Uma esteira real, para leitura |
| `testes/` | O que se prova sozinho |

## A documentação

| Documento | Para quê |
| --- | --- |
| [Instalação](docs/instalacao.md) | Passo a passo, o que cada passo toca, e o que fazer quando falha |
| [Organização no ClickUp](docs/clickup.md) | Os dez status, quem manda em quê, como escrever sem falsificar autoria |
| [Operação no dia a dia](docs/operacao.md) | Ler o quadro, despachar, reconhecer que a esteira espera **você** |
| [Para quem chega](docs/para-quem-chega.md) | Entrou num projeto que já usa isto? Comece por aqui |
| [Segurança](docs/seguranca.md) | A cerca, o que ela cobre e o que ela não cobre |
| [Host Linux](docs/host-linux.md) | Rodar sozinho num servidor |
| [Medição](docs/medicao.md) | O que a esteira produziu: sessões, retrabalho, espera humana, tokens e código |
| **[Aprendizados](docs/aprendizados.md)** | **Vinte e duas coisas que custaram tempo descobrir** |

**Comece pelos aprendizados se quiser saber se isto vale a pena.** É a parte que não se
inventa: cada item é um problema que já aconteceu, com o número exato, o comando que
confirma e o que foi feito para não repetir. Ferramenta se escreve de novo; essas vinte e duas
descobertas, não.

## O que já se sabe

Cada linha abaixo custou tempo. Elas não são preferências de estilo: são consertos de
coisas que quebraram, e a história completa de cada uma está nos
[Aprendizados](docs/aprendizados.md).

- **A cerca é um gancho, não uma lista de permissões.** A lista foi tentada primeiro e
  **não funcionou**: uma negação injetada pela esteira perdeu para uma permissão idêntica
  que a pessoa já tinha. O gancho vê o comando inteiro e não é anulável por ninguém.
- **Dependência entre tarefas mora no repositório, não no quadro.** Dependência é decisão
  técnica e precisa ser revisada com o código. Campo de ferramenta de gestão muda sozinho.
- **Tarefa que está no quadro e não está no arquivo nunca é executada.** Esteira que roda o
  que aparece na lista é esteira que qualquer um dispara sem querer.
- **Portão inventado é pior que portão ausente.** Se o projeto não declara comando de teste,
  o portão de teste não existe — dizer isso à pessoa é melhor do que adivinhar um comando
  que vai falhar pelo motivo errado na primeira sessão.
- **O status "parado" não é enfeite.** Sem ele, o quadro mostra "revisando" e todo mundo
  acha que alguém está revisando, quando na verdade a esteira espera **você**.
- **Confira a autoria antes de escrever no quadro.** Uma aprovação já foi publicada assinada
  por outra pessoa, porque a escrita saiu por um caminho autenticado com a sessão de outro.
  Aprovação atribuída a quem não aprovou é falsificação de registro, mesmo sem má intenção.
- **Orçamento de memória se corrige por medida, não por palpite.** Um palpite sete vezes
  acima do real fez uma máquina admitir uma sessão por vez quando cabiam oito.
- **Encerramento do ambiente não é opcional.** Sem ele, cada sessão deixa serviço vivo para
  trás: já foram 27 pilhas segurando 8,8 GB e uma esteira inteira travada.
- **A base local do repositório envelhece sem avisar.** Atribuir trabalho pelo intervalo
  `base..branch` mente quando a base está atrasada; a atribuição correta sai do merge.
- **Antes de assumir que falta um recurso, procure o mesmo fato num rastro que você já
  produz.** O tempo em cada status do ClickUp é pago; os comentários das tarefas dão a mesma
  linha do tempo de graça, e ainda dizem o que aconteceu e quem assinou.

## O que uma corrida real produziu

Números medidos pela própria ferramenta, numa esteira de front-end de 30 unidades:

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
pela média engana.

Como reproduzir na sua esteira: `orq-medir coletar && orq-medir resumo`.

## O que isto NÃO faz

- **Não é contenção contra código hostil.** A cerca reduz o raio de dano de um agente que
  erra. Repositório com dependência não confiável está fora do que ela protege.
- **Só fala com o ClickUp.** Outras ferramentas de gestão ficam de fora; a fronteira está
  isolada para que um dia isso seja trabalho, não reescrita.
- **Não decide por você.** Fechar cartão, declarar unidade, aprovar entrega e resolver
  conflito de especificação continuam sendo humanos.
- **A cobertura de testes é parcial, e o recorte é deliberado.** Tem bateria completa no
  medidor, nas funções puras de leitura de memória e na cerca — cerca com defeito deixa
  tudo passar e dá confiança falsa. O laço de despacho em si continua provado pelo pré-voo
  honesto e pela primeira esteira real, não por teste.
- **Não migra sua máquina sozinho.** Se você já usava uma versão anterior, a troca é um
  passo consciente. Está em [Instalação](docs/instalacao.md).
