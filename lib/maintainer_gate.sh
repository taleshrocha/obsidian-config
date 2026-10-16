#!/bin/sh
# Só o mantenedor altera este repositório. Ele marca o próprio clone uma vez:
#   git config obsidian-config.maintainer true
# Quem usa o obsidian-config (devs de um time, agentes de IA) não comita nem publica aqui:
# descreve o problema e entrega o patch ao mantenedor.
if [ "$(git config --get obsidian-config.maintainer)" = "true" ]; then
    exit 0
fi
cat >&2 <<'MSG'
Commit bloqueado: este clone do obsidian-config não é de mantenedor.
Só o dono do repositório comita aqui. Não use --no-verify nem contorne.
Para propor uma correção: salve `git diff` num arquivo FORA do repositório,
descreva o problema e envie ao mantenedor. Depois descarte a alteração local
(`git restore .`; se já comitou, `git reset --hard @{u}`).
MSG
exit 1
