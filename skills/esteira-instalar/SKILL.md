---
name: esteira-instalar
description: Use para pôr a esteira para funcionar num projeto que ainda não a tem — examinar o repositório, propor os estágios e os portões a partir do que ele já declara, criar os status no ClickUp, e só entregar quando o pré-voo fechar verde. Use quando pedirem para "instalar a esteira aqui", "configurar o orquestrador neste projeto", "adotar isso no nosso repositório", ou quando alguém quiser saber se este projeto tem como rodar sessões governadas.
---

# Instalar a esteira num projeto

Você vai escrever no repositório de outra pessoa. Vale a regra das skills que constroem:
**examinar primeiro, apresentar o que pretende escrever, escrever só depois do sim.**

## 1. Examinar antes de perguntar

```bash
cd <raiz do repositório>
orq init --simular
```

Ele lê o repositório e mostra o que descobriu, dizendo de onde tirou cada coisa: branch
base, diretório de trabalho, gerenciador de pacotes, e os scripts que o projeto **já**
declara. Nada é escrito.

## 2. Apresentar a proposta a uma pessoa

Em português comum, sem código como sujeito de frase. Quatro coisas:

- quais estágios a esteira vai ter, e o que cada um significa;
- quais portões — e **de onde saíram**;
- onde ficam as cópias de trabalho (fora do repositório, e por quê);
- quanta memória por estágio, e que esse número se corrige por medida depois;
- **o que prova que a publicação passou**, depois do merge — veja abaixo.

## 2b. Pergunte quem faz o quê, e o que prova

A ferramenta não adivinha estas quatro, e errar qualquer uma gasta sessão:

- **Tem verificação automática?** Se sim, qual comando a consulta
  (`gh run list --branch main --limit 3`, um script de deploy, um webhook). Isso vira
  `verificacao_automatica` e é o passo 7 do integrador. **Se não tem, deixe vazio** —
  a ordem de serviço passa a dizer que não há o que procurar. Nunca presuma que tem.
- **Como se publica?** Se existe um comando só para isso, nomeie-o no
  `publish_note` do estágio de integração. Ele vence o procedimento genérico, e é a
  diferença entre o integrador executar e o integrador improvisar `rsync`.
- **Tem ambiente fechado para provar comportamento?** Se sim, `esteira-sandbox`.
- **Quais estágios são de gente?** Um estágio que uma pessoa faz não deve ser
  despachado: declare-o fora dos estágios da esteira ou marque as unidades como
  `hands-on` e ponha o modo em `skip_modes`.

## 3. Portões descobertos, nunca inventados

Se o projeto não declara um comando de teste, **o portão de teste não existe**. Diga isso à
pessoa em vez de inventar um comando: portão inventado falha por motivo errado na primeira
sessão, e o time conclui que a ferramenta não presta.

## 4. Escrever, depois do sim

```bash
orq init --lista <listId>
```

Sai um `.orchestrator/pipeline.toml` comentado, para revisão humana. Os comentários
explicam cada escolha — não os apague.

**Uma decisão precisa de atenção especial:** se as dependências entre as unidades forem de
**código**, `[pipeline.dependency]` tem de ser `after = "integrate"`. Com `after = "review"`
a unidade é despachada antes de o código da dependência existir na base, e a sessão é gasta
à toa. Isso já aconteceu.

## 5. Os status no ClickUp

```bash
orq-clickup status-provisionar <listId>              # simula e mostra tudo
orq-clickup status-provisionar <listId> --aplicar
```

Leia o aviso sobre herança de status antes de aplicar. Se a lista herda da pasta, criar
status nela muda a lista — e talvez o certo seja definir na pasta.

## 6. Encerramento é obrigatório se o projeto sobe serviço

Se trabalhar neste projeto exige subir banco, servidor ou qualquer processo, o bloco
`teardown` **não é opcional**. Chame a skill `esteira-sandbox` para construí-lo. Sem isso,
cada sessão deixa um ambiente vivo para trás: já foram 27 pilhas segurando 8,8 GB e uma
esteira inteira travada.

## 7. Entregar com o pré-voo verde

```bash
orq doctor
```

Ele prova cada dependência por chamada real e mostra a evidência. Só entregue quando fechar
verde — e mostre a saída para a pessoa, linha por linha. Se algo ficar vermelho, diga o que
é e o que falta, em português comum.

## O que declarar depois

As unidades (`[[task]]`) são declaradas por uma pessoa, no fim do arquivo. Tarefa que existe
no ClickUp e não está declarada aparece no quadro como deriva e **nunca** é executada. Isso
é proposital.
