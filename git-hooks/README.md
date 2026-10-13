# Git hooks dos vaults

O `install.py` aponta `core.hooksPath` do vault (e dos vaults montados) para esta pasta. O Git roda `pre-commit` via `sh` em Linux, macOS e Windows (Git for Windows). Esse wrapper chama `pre_commit.py` com o Python disponível.

`pre_commit.py`:
1. Com `generate_agent_files` ativo, regenera `CLAUDE.md`, `GEMINI.md` e `AGENTS.md` quando a política ou as regras privadas mudam, ou quando eles estão dessincronizados.
2. Roda `bin/vault-validate` com a config do vault. Erro de estrutura, frontmatter, link, segredo, privacidade ou vazamento para vault montado aborta o commit.
3. Roda as verificações locais de `~/.config/obsidian-config/pre-commit.d/<vault_name>/`, como o guard do vault pessoal. Elas não são versionadas.
