# Segurança

## O que a cerca barra

Toda sessão sobe com uma cerca: um gancho que roda **antes** de cada uso de ferramenta e
pode barrar. Ela vê o comando inteiro.

| Não passa | Por quê |
| --- | --- |
| Publicar em qualquer branch que não seja o próprio da unidade | Publicar o seu branch é permitido; publicar a base ou o branch de outra unidade, nunca. |
| Fundir (`gh pr merge`), sob qualquer forma | Fundir é do gate humano, sem exceção — nenhuma sessão funde, mesmo dentro do próprio branch. |
| `git merge` trazendo a base para dentro de si mesma | Fundir dentro da base é integração, e integração é do gate humano agora. |
| Publicar com força, espelho ou remoção de branch | Reescrever histórico é decisão humana, mesmo no próprio branch. |
| Abrir PR para uma base diferente da declarada na esteira | PR para o lugar errado é trabalho perdido descoberto tarde. |
| Elevar privilégio (`sudo`) | Se a tarefa exige administrador, ela exige uma pessoa. |
| Publicar pacote, publicar uma release | Irreversível. |
| Baixar e executar script da internet | Se a ferramenta é necessária, ela se declara no `CLAUDE.md` do projeto, onde alguém revisa. |
| Apagar recursivamente fora da própria cópia de trabalho | O dano fica contido no que é descartável. |
| Ler ou escrever a credencial pessoal, o registro de confiança de pastas, ou o banco da esteira | Uma sessão que pode reescrever a cerca ou o estado não tem cerca nem estado confiável. |

Quando a cerca barra, ela diz **o motivo e o que fazer** — a sessão deve concluir
(`orq advance`) ou travar (`orq hold`), nunca contornar.

## Por que um gancho, e não uma lista de permissões

Foi decidido por experimento, em 02/09/2026.

A primeira versão usava a lista de negação do próprio arquivo de configuração. Ela **não
funcionou**: uma negação de `git push` injetada pela esteira não venceu uma permissão
idêntica que a pessoa já tinha nas configurações dela. O comando executou.

E regra por prefixo nunca pegaria `cd /outro/lugar && git push`, que é uma linha de shell
trivial.

O gancho vê o comando inteiro, roda sempre, e não é anulável por permissão de ninguém.

**A regra de publicação mudou de "por etapa" para "por branch da própria unidade".** No
modelo antigo, só a sessão de integração publicava. Com um papel só, não existe mais sessão
de integração: qualquer sessão pode publicar o **seu próprio** branch — é o passo 6 do
briefing — mas nenhuma funde. A distinção deixou de ser "quem você é" e passou a ser "para
onde você está publicando".

## As outras travas

**A confiança de pasta é herdada, nunca concedida.** Cada cópia de trabalho é um caminho
novo. A esteira herda a confiança do repositório base; se o base não for confiável, ela
**recusa** em vez de decidir por você.

**As credenciais vivem fora de qualquer repositório**, com permissão restrita. O instalador
se recusa a prosseguir se encontrar token dentro da árvore clonada.

**O semeador do ambiente fechado recusa endereço que não seja local.** Sem exceção e sem
bandeira que destrave. Ele cria usuários com senha conhecida; apontá-lo para um ambiente de
verdade seria abrir uma porta dos fundos.

**O pré-voo recusa despachar sem a cerca**, e registra a impressão digital dela para notar
adulteração.

**O acompanhamento remoto fica ligado e nomeado.** Isso é medida de segurança, não
conveniência: é como uma pessoa vê e interrompe, de outro dispositivo, uma sessão que está
agindo sozinha.

## Uma cerca com defeito é pior do que nenhuma

A primeira versão da cerca tinha um erro de leitura do evento que a deixava **inerte**:
todos os casos passavam, e nada indicava problema. Cerca quebrada dá confiança falsa.

Por isso existe uma bateria de casos, e o instalador se recusa a instalar se ela falhar:

```bash
./testes/cerca.sh
```

Metade dos casos é o que ela precisa barrar; metade é o trabalho normal que ela precisa
deixar passar. Os dois lados importam: uma cerca que barra tudo também não serve.

## O limite honesto

**Isto reduz o raio de dano de um agente que erra. Não é contenção contra código hostil.**

Uma sessão executa o código do projeto — testes, compilação, dependências. Se o projeto tem
dependência não confiável, a cerca não protege contra isso: o código malicioso roda dentro
do que é permitido.

Quem for adotar em repositório com dependência de origem duvidosa precisa de outra camada:
container, máquina descartável, rede fechada. A esteira não substitui isso.

## Se algo der errado

```bash
tmux kill-session -t orq-loop-<esteira>   # para de despachar
orq status                                # o que ainda está vivo
orq stop <unidade>                        # encerra uma sessão sem mudar o status
```

O trabalho feito fica: cada unidade tem seu branch publicado (se chegou a publicar), e a
worktree só é removida quando a unidade chega a `pronto` ou `bloqueado` — nunca por parar o
laço.
