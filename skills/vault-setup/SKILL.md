---
name: vault-setup
type: skill
description: Configura e confere o ambiente de um dev no obsidian-config: credenciais Git (token no cofre do sistema), credential helper, vault e MCP. Use quando o usuário pedir "configure minhas credenciais", "setup do vault", ou quando um git pull/push do vault falhar por autenticação.
---

# Setup do ambiente obsidian-config

Objetivo: deixar as credenciais Git do vault funcionando em qualquer máquina (Linux, macOS, Windows), sem caminho de arquivo fixo e sem o agente ver o token.

## Regras

1. Nunca peça o token no chat, nunca leia nem imprima o valor, nunca grave em nota, `.git/config` ou log.
2. Nunca suponha `~/.config/...` de outra máquina. O token vem da variável de ambiente (`token_env`), de arquivo (`token_file`) ou do cofre de credenciais do git, nessa ordem.
3. Não use SSH para hosts com regra `git_https_auth`.
4. Não edite nem comite no repositório `obsidian-config` (só o mantenedor). Problema na ferramenta: descreva e entregue o patch ao operador.

## Passos

1. Diagnóstico, sem prompts e seguro para o agente:
   ```
   vault auth setup --check
   ```
   Mostra se há credential helper e, por host de `git_https_auth`, de onde vem o token (ou que falta).
2. Tudo `✓`: pare. Confirme com um `git ls-remote` ou `git pull --rebase` no vault de time e informe o resultado.
3. Faltou helper ou token: o setup pede digitação oculta, então o operador roda ele mesmo num terminal real (no Claude Code, prefixe com `!`):
   ```
   vault auth setup
   ```
   Ele ativa o helper do sistema (`manager` no Windows, `osxkeychain` no macOS, `libsecret` no Linux), pede o token com entrada oculta e verifica que ficou guardado.
4. Sem regra `git_https_auth` no `.vault/config.json`: acrescente `{"host_contains": "<host>", "user": "oauth2"}` na lista (config privada do vault, nunca no obsidian-config) e volte ao passo 1.
5. Linux sem libsecret: instale `git-credential-libsecret` (pacote `libsecret-1-0` e `libsecret-1-dev` para compilar, ou o pacote `git` da distro que o inclua), ou use `token_env` com a variável definida no perfil do shell.
6. Termine rodando `vault auth status` e reporte, por host, só `disponível (origem)` ou `sem token`.
