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
confirma e o que foi feito para não repetir. Ferramenta se escreve de novo; essas vinte
descobertas, não.

## O que isto NÃO faz

- **Não é contenção contra código hostil.** A cerca reduz o raio de dano de um agente que
  erra. Repositório com dependência não confiável está fora do que ela protege.
- **Só fala com o ClickUp.** Outras ferramentas de gestão ficam de fora; a fronteira está
  isolada para que um dia isso seja trabalho, não reescrita.
- **Não decide por você.** Fechar cartão, declarar unidade, aprovar entrega e resolver
  conflito de especificação continuam sendo humanos.
- **Não tem suíte de testes do próprio motor.** Decisão consciente do dono: o pré-voo
  honesto é a prova, e a primeira esteira real é o teste. As exceções são as funções puras
  de leitura de memória e a bateria de casos da cerca — porque cerca com defeito deixa tudo
  passar e dá confiança falsa.
- **Não migra sua máquina sozinho.** Se você já usava uma versão anterior, a troca é um
  passo consciente. Está em [Instalação](docs/instalacao.md).
