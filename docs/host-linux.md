# Rodar num servidor Linux

Sai da sua máquina e passa a rodar sozinho — inclusive quando você está dormindo.

O roteiro executável está na skill `esteira-host`, em `skills/esteira-host/provisionar.sh`.
Ele é idempotente: rodar de novo não estraga nada.

```bash
sudo bash provisionar.sh [usuário]     # padrão: orq
```

## O que ele não faz, e por quê

Três coisas exigem uma pessoa:

- **autenticar o agente** — o login vem da assinatura de alguém;
- **registrar a chave pública** no serviço de código;
- **aceitar o modo automático** na primeira execução.

Automatizar qualquer uma delas significaria guardar credencial de alguém num script.

## Depois de provisionar, quatro cuidados

**Entre como o usuário da esteira, nunca como root.** O teto de memória vive na fatia
daquele usuário. Um comando vindo de sessão de root escapa da fatia, e o teto deixa de
valer — a máquina inteira fica exposta a algo que deveria estar contido.

**Configure um destino de aviso.** Sem tela, a notificação do sistema não existe e o
registro em arquivo ninguém lê: a espera humana fica silenciosa e a esteira parece travada
sem motivo.

```bash
export ORQ_AVISO_DESTINO=clickup
export ORQ_AVISO_CANAL=...        # a sua conversa direta serve
export ORQ_AVISO_WORKSPACE=...
export ORQ_AVISO_MENCIONAR=...    # seu id, para a mensagem te marcar
```

**Trave a versão do gerenciador de pacotes.** Quando o preparo de uma cópia de trabalho
falhar instalando dependências, olhe a versão do gerenciador **antes** de acusar o projeto.
Versões novas recusam certos arquivos de trava, e o erro parece do projeto.

**Nunca ponha o token do agente no ambiente.** Ele vence o login interativo, desliga o
acompanhamento remoto e rebaixa o modelo do plano — tudo em silêncio.

## Olhe a fatia, não a máquina

```bash
orq host
```

Em Linux com systemd, o que limita a esteira é o teto do usuário, não a memória da máquina.
Já houve fatia sufocada — swap cheio, mais de um milhão de freadas por memória — com o
medidor da máquina anunciando 16 GB livres.

E lembre: **containers ficam fora da fatia**. Eles rodam sob o serviço do Docker, que é
root. Podem estar presos ao endereço local e ainda assim não serem contidos pelo teto.

## Pronto quando

```bash
orq doctor
```

Ele prova de verdade: pergunta ao agente, chama o ClickUp, cria e remove uma cópia de
trabalho, abre e fecha uma sessão. Só considere o servidor pronto quando fechar verde.
