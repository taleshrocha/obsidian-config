# MCP server `obsidian-vault`

Servidor MCP (stdio, JSON-RPC 2.0, sem dependências npm) que expõe o vault aos agentes de IA.

O vault vem de `OBSIDIAN_VAULT_PATH` ou de `~/.config/obsidian-config/config.json` (gravado pelo `install.sh`).

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `search_vault` | Busca textual em conteúdo, frontmatter e caminhos |
| `read_metadata` | Lê só o frontmatter YAML |
| `get_outline` | Árvore de cabeçalhos da nota |
| `read_section` | Lê só uma seção |
| `read_note` | Nota completa |
| `list_notes` | Filtra por `type`, `organization` ou pasta |
| `get_backlinks` | Notas que apontam para uma nota |
| `get_architecture_topology` | Servidores, serviços, aplicações e arquitetura de uma organização |
| `create_change_record` | Cria `08 - Mudancas/YYYY/CHG-YYYY-MM-DD-NNN - Título.md` |
| `append_daily_log` | Acrescenta entrada em `13 - Reunioes/YYYY-MM-DD.md` |
| `open_in_gui` | Abre a nota no Obsidian via `obsidian-cli` |
| `validate_vault` | Roda `bin/vault-validate` |

## Registro manual

O `install.sh` e o `sync-agents` já registram. Para registrar à mão:

```bash
claude mcp add obsidian-vault --scope user -e OBSIDIAN_VAULT_PATH="$HOME/Vault" -- node "$HOME/obsidian-config/mcp-server/index.js"
codex mcp add obsidian-vault --env OBSIDIAN_VAULT_PATH="$HOME/Vault" -- node "$HOME/obsidian-config/mcp-server/index.js"
gemini mcp add -e OBSIDIAN_VAULT_PATH="$HOME/Vault" obsidian-vault node "$HOME/obsidian-config/mcp-server/index.js"
```
