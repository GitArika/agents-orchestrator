#!/usr/bin/env bash
# Prepara um host Linux (systemd, cgroup v2) para hospedar o orquestrador `orq`.
# Idempotente: rodar de novo não estraga nada.
#
#   sudo bash provisionar-host.sh [USUARIO]
#
# O que ele NÃO faz, de propósito, porque exige uma pessoa:
#   * autenticar o Claude Code (token OAuth vem da sua assinatura)
#   * registrar a chave pública no GitHub
#   * aceitar o modo `auto` na primeira execução
set -euo pipefail

U="${1:-orq}"
H="/home/$U"

say() { printf '\n\033[1;35m▸ %s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "rode como root"; exit 1; }

say "1. usuário de serviço '$U'"
if id "$U" >/dev/null 2>&1; then ok "já existe (uid $(id -u "$U"))"
else useradd --create-home --home-dir "$H" --shell /bin/bash "$U"; ok "criado"; fi
UID_N="$(id -u "$U")"

say "2. árvore de trabalho"
install -d -o "$U" -g "$U" -m 755 \
  "$H/repos" "$H/worktrees" \
  "$H/.claude" "$H/.claude/orchestrator" "$H/.claude/orchestrator/state" \
  "$H/.claude/orchestrator/hooks" "$H/.claude/orchestrator/templates"
ok "$H/{repos,worktrees,.claude/orchestrator}"

say "3. teto de recursos — user-$UID_N.slice"
# Toda a árvore de processos do usuário cai nesta slice, inclusive o servidor
# tmux e cada sessão do Claude Code. É por isso que o teto vai AQUI e não num
# wrapper: não há como uma sessão escapar dele.
#   MemoryHigh = onde o kernel começa a apertar (recupera página, não mata)
#   MemoryMax  = onde ele mata. Folga proposital entre os dois.
install -d -m 755 "/etc/systemd/system/user-$UID_N.slice.d"
cat > "/etc/systemd/system/user-$UID_N.slice.d/orq-limites.conf" <<EOF
# Teto do orquestrador. A PROD divide esta máquina; sem teto, um \`pnpm install\`
# em disparada dentro de uma sessão disputa memória com o Postgres.
[Slice]
MemoryHigh=14G
MemoryMax=18G
MemorySwapMax=4G
CPUQuota=600%
TasksMax=8192
EOF
systemctl daemon-reload
ok "MemoryHigh=14G MemoryMax=18G CPUQuota=600%"

say "4. linger (sessões sobrevivem ao fim do SSH)"
loginctl enable-linger "$U"; ok "ligado"

say "5. Claude Code (npm, prefixo do usuário — auto-update sem root)"
sudo -u "$U" -H bash -lc '
  set -e
  npm config set prefix "$HOME/.npm-global" >/dev/null
  if command -v "$HOME/.npm-global/bin/claude" >/dev/null; then
    echo "  já instalado: $($HOME/.npm-global/bin/claude --version 2>&1 | head -1)"
  else
    npm install -g @anthropic-ai/claude-code >/dev/null 2>&1
    echo "  instalado: $($HOME/.npm-global/bin/claude --version 2>&1 | head -1)"
  fi'
ok "claude em $H/.npm-global/bin"

say "6. PATH e ambiente do usuário"
# O `claude` vive no prefixo npm do usuário, que não está em PATH nenhum por
# padrão. Duas amarras, porque uma só não cobre os dois modos de uso:
#   * link em /usr/local/bin — vale para `ssh $U@host "orq doctor"`, que roda
#     um shell NÃO-interativo: o .bashrc do Ubuntu tem um `return` no topo para
#     esse caso, então qualquer export ao fim do arquivo nunca é lido.
#   * bloco no .profile/.bashrc — carrega os segredos do .orq-env nas sessões
#     de verdade (tmux, login), onde o Claude Code precisa do token no ambiente.
ln -sf "$H/.npm-global/bin/claude" /usr/local/bin/claude
for f in "$H/.profile" "$H/.bashrc"; do
  touch "$f"; chown "$U:$U" "$f"
  if ! grep -q 'ORQ_PATH_MARK' "$f"; then
    # No TOPO: o guarda de shell não-interativo do Ubuntu fica na primeira
    # dezena de linhas, e tudo depois dele é invisível para `ssh host comando`.
    tmp="$(mktemp)"
    { cat <<EOF
# ORQ_PATH_MARK — orquestrador
export PATH="\$HOME/.npm-global/bin:/usr/local/bin:\$PATH"
[ -f "\$HOME/.orq-env" ] && . "\$HOME/.orq-env"

EOF
      cat "$f"; } > "$tmp"
    mv "$tmp" "$f"; chown "$U:$U" "$f"; chmod 644 "$f"
  fi
done
if [ ! -f "$H/.orq-env" ]; then
  cat > "$H/.orq-env" <<'EOF'
# Segredos e ajustes do orquestrador. Carregado por .profile e .bashrc.
# Preencha o token do Claude Code (gerado com `claude setup-token` na sua máquina):
# export CLAUDE_CODE_OAUTH_TOKEN="..."
#
# Canal de aviso para host sem desktop: recebe (título, mensagem) em argv.
# export ORQ_NOTIFY_CMD="/usr/local/bin/orq-avisar"
EOF
  chown "$U:$U" "$H/.orq-env"; chmod 600 "$H/.orq-env"
fi
ok ".profile, .bashrc, .orq-env (0600)"

say "7. chave SSH para o GitHub"
install -d -o "$U" -g "$U" -m 700 "$H/.ssh"
if [ -f "$H/.ssh/id_ed25519" ]; then ok "chave já existe"
else
  sudo -u "$U" ssh-keygen -t ed25519 -N '' -C "orq@$(hostname)" -f "$H/.ssh/id_ed25519" >/dev/null
  ok "gerada"
fi
sudo -u "$U" bash -c "ssh-keyscan -t ed25519 github.com 2>/dev/null | sort -u -o '$H/.ssh/known_hosts.gh' - && \
  touch '$H/.ssh/known_hosts' && cat '$H/.ssh/known_hosts.gh' >> '$H/.ssh/known_hosts' && \
  sort -u '$H/.ssh/known_hosts' -o '$H/.ssh/known_hosts' && rm -f '$H/.ssh/known_hosts.gh'"
chmod 600 "$H/.ssh/known_hosts"
ok "github.com em known_hosts"

say "8. git do usuário (governança de autoria)"
sudo -u "$U" git config --global user.name  "Ariel Evangelista"
sudo -u "$U" git config --global user.email "ariel.evangelista@outlook.com"
sudo -u "$U" git config --global init.defaultBranch main
ok "autor = Ariel Evangelista <ariel.evangelista@outlook.com>"

say "PRONTO — falta o que só uma pessoa pode fazer"
echo
echo "  a) registrar esta chave no GitHub (deploy key ou conta de máquina):"
echo
sed 's/^/     /' "$H/.ssh/id_ed25519.pub"
echo
echo "  b) pôr o token do Claude Code em $H/.orq-env:"
echo "     export CLAUDE_CODE_OAUTH_TOKEN=\"...\"   # gere com: claude setup-token"
echo
echo "  c) aceitar o modo auto uma vez:  sudo -u $U -i claude --permission-mode auto"
echo
