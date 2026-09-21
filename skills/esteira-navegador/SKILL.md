---
name: esteira-navegador
description: Use quando a prova exigir um navegador de verdade — rolagem horizontal, alvo de toque, foco que escapa de um painel, contraste, política de conteúdo, camada de sobreposição, ou qualquer critério visual que ambiente simulado de teste não consegue provar. Monta a verificação em navegador headless com auditoria de acessibilidade para ESTE projeto, instalada fora do repositório dele. Use também quando uma especificação declarar um critério "improvável neste repositório" — quase sempre ele é provável, só não com as ferramentas que estavam à mão.
---

# Montar a prova em navegador deste projeto

## Quando isto é necessário

Ambiente simulado de teste não faz layout, não tem camada de sobreposição e não tem política
de conteúdo. Um navegador de verdade tem os três. Se o critério de aceite fala de rolagem,
tamanho de alvo de toque, foco que escapa, contraste ou sobreposição, o teste de unidade
**não prova** — e declarar o critério como "improvável" é desistir cedo demais.

## A regra que vem antes de todas

**Instale fora do repositório do projeto.**

O preparo de cada cópia de trabalho usa instalação congelada de dependências. Acrescentar um
navegador às dependências do projeto quebraria a instalação de **toda** cópia em voo — e o
erro apareceria como falha de preparo em unidades que não têm nada a ver com isso.

Instale numa pasta de ferramentas do usuário e exponha um comando. O projeto não fica
sabendo que ele existe.

## 1. Descobrir como se entra neste produto

Não assuma um fluxo de login. Descubra:

- qual a rota da tela de acesso;
- quais os seletores dos campos e do botão;
- o que caracteriza "entrou" (mudança de rota, um elemento que aparece, um token guardado);
- se existe segundo fator, e como desligá-lo no ambiente fechado.

A credencial vem do **ambiente fechado** (`esteira-sandbox`), com usuários inventados. Nunca
credencial de gente de verdade, nunca base de homologação.

## 2. Um comando de diagnóstico próprio

A ferramenta precisa saber dizer que está pronta, antes de qualquer sessão confiar nela:
navegador instalado, versão, consegue abrir uma página em branco, consegue alcançar o
endereço do ambiente fechado. Sessão que descobre no meio do trabalho que o navegador não
funciona já gastou a sessão.

## 3. O que provar

- **Layout**: rolagem horizontal onde não deveria haver, quebra em telas estreitas.
- **Alvo de toque**: tamanho mínimo dos elementos clicáveis.
- **Foco**: se ele escapa de um painel ou de uma janela sobreposta.
- **Contraste e acessibilidade**: auditoria automática cobre boa parte.
- **Política de conteúdo**: violação só aparece em navegador de verdade.

Guarde as capturas de tela junto com o resultado — quem revisa precisa ver, não acreditar.

## 4. Ligue ao encerramento

Se a prova sobe um servidor, ele entra no `teardown` da esteira. Navegador headless que
ninguém fecha também é processo abandonado.
