# Segurança

## O que a cerca barra

Toda sessão sobe com uma cerca: um gancho que roda **antes** de cada uso de ferramenta e
pode barrar. Ela vê o comando inteiro.

| Não passa | Por quê |
| --- | --- |
| Publicar ou fundir fora da etapa de integração | Publicar é de uma etapa só. As outras commitam na própria cópia e param. |
| Publicar com força, espelho ou remoção de branch | Reescrever histórico é decisão humana. Nem a integração faz isso. |
| Elevar privilégio (`sudo`) | Se a tarefa exige administrador, ela exige uma pessoa. |
| Publicar pacote | Irreversível. |
| Baixar e executar script da internet | Se a ferramenta é necessária, ela se declara no preparo, onde alguém revisa. |
| Apagar recursivamente fora da própria cópia de trabalho | O dano fica contido no que é descartável. |
| Ler ou escrever a credencial pessoal e o registro de confiança de pastas | Uma sessão que pode reescrever a cerca não tem cerca. |

Quando a cerca barra, ela diz **o motivo e o que fazer** — a sessão deve concluir, reprovar
ou travar, nunca contornar.

## Por que um gancho, e não uma lista de permissões

Foi decidido por experimento, em 02/09/2026.

A primeira versão usava a lista de negação do próprio arquivo de configuração. Ela **não
funcionou**: uma negação de `git push` injetada pela esteira não venceu uma permissão
idêntica que a pessoa já tinha nas configurações dela. O comando executou.

E regra por prefixo nunca pegaria `cd /outro/lugar && git push`, que é uma linha de shell
trivial.

O gancho vê o comando inteiro, roda sempre, e não é anulável por permissão de ninguém.

**E ele conhece a etapa** — o que corrigiu um segundo erro: barrar `git push` por inteiro
quebraria justamente a integração, que é quem publica.

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
orq loop-stop            # para de despachar
orq status               # o que ainda está vivo
orq stop <tarefa>        # encerra uma sessão
```

O trabalho feito fica: cada tarefa tem seu branch, e as cópias de trabalho não são apagadas
ao parar.
