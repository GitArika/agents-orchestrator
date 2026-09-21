---
name: esteira-host
description: Use para preparar uma máquina Linux para hospedar a esteira rodando sozinha — usuário próprio, teto de memória e processador, Docker, versões travadas, e as armadilhas que já custaram tempo nesse caminho. Use quando pedirem para mudar a esteira para um servidor, provisionar uma máquina nova, ou quando a esteira num servidor estiver se comportando diferente da máquina de desenvolvimento.
---

# Hospedar a esteira num servidor

O roteiro executável está em `provisionar.sh`, ao lado deste arquivo. Ele é idempotente:
rodar de novo não estraga nada.

```bash
sudo bash provisionar.sh [usuário]     # padrão: orq
```

## O que ele NÃO faz, de propósito

Estas três exigem uma pessoa e não podem ser automatizadas sem quebrar algo:

- **autenticar o agente** — o login vem da assinatura de alguém;
- **registrar a chave pública** no serviço de código;
- **aceitar o modo automático** na primeira execução.

## As armadilhas

**Entre como o usuário da esteira, nunca como root.** O teto de recursos vive na fatia
daquele usuário. Um comando vindo de sessão de root escapa dela, e o teto simplesmente
deixa de valer — a máquina inteira fica exposta a uma esteira que deveria estar contida.

**Containers ficam fora do teto.** Eles rodam sob o serviço do Docker, que é root. Podem
estar presos ao loopback e ainda assim não serem contidos pela fatia. Conte-os à parte
quando for dimensionar.

**Trave a versão do gerenciador de pacotes.** Quando o preparo de uma cópia de trabalho
falhar instalando dependências, **olhe a versão do gerenciador antes de acusar o projeto**:
versões novas recusam lockfile com dependência sem hash de integridade, e o erro parece do
projeto. Já custou uma tarde.

**Nunca ponha o token do agente no ambiente.** Ele vence o login interativo, desliga o
acompanhamento remoto (a sessão nem aparece na lista do celular) e rebaixa o modelo do
plano. Diagnostique sempre por `/status` dentro da sessão, nunca por `claude auth status`,
que diz que está logado nos dois casos.

**Aviso não chega sozinho num servidor.** Sem tela, notificação de sistema não existe e o
registro em arquivo ninguém lê: a espera humana fica silenciosa e a esteira parece travada
sem motivo. Configure um destino de verdade:

```bash
export ORQ_AVISO_DESTINO=clickup
export ORQ_AVISO_CANAL=...      # a sua conversa direta serve
export ORQ_AVISO_WORKSPACE=...
```

**Olhe a fatia, não a máquina.** `orq host` lê o teto do usuário em Linux com systemd. Já
houve fatia sufocada — swap cheio, mais de um milhão de freadas por memória — com o medidor
da máquina anunciando 16 GB livres.

## Depois de provisionar

```bash
orq doctor          # prova cada dependência por chamada real
orq host            # o que limita esta máquina
```

Só considere o servidor pronto quando o pré-voo fechar verde. Ele prova de verdade: pergunta
ao agente, chama o ClickUp, cria e remove uma cópia de trabalho, abre e fecha uma sessão.
