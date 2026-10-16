# Contrato para agentes de IA · obsidian-config

Este repositório é **público**. Ele contém ferramentas e configuração base para vaults Obsidian. Nenhum dado pessoal entra aqui: caminhos de home, nomes de organizações, hosts, IPs, e-mails, pessoas, regras pessoais ou conteúdo de notas.

## Onde fica cada coisa

| Precisa mudar | Onde |
|---|---|
| Comportamento de ferramenta (validação, CLI, MCP, hooks, install) | este repositório |
| Regra genérica para agentes | `agents/base-instructions.md` (curta, vai para as instruções globais) ou `agents/policy.md` (política completa) |
| Organização, mount, host Git, servidor padrão, tópicos da política | `<vault>/.vault/config.json` (privado) |
| Regra pessoal para agentes | nota `agent_rules_note` do vault (privado) |
| Template genérico | `templates/` (o install copia só os ausentes) |

Se a mudança só faz sentido para um usuário, ela vai para o vault dele. Neste repositório entra só o mecanismo, ou seja, a opção de config, nunca o valor pessoal.

## Mapa

- `lib/vaultcfg.py`: resolve o vault e carrega `.vault/config.json`. Toda ferramenta Python usa isso.
- `bin/`: `vault` (CLI), `vault-validate`, `vault-health`, `vault-sources`, `vault-semantic-search`, `generate-canvas`, `sync-agents`, `shared-vault-guard`. Todos Python e sem dependência externa, exceto a busca semântica (`numpy`).
- `mcp-server/index.js`: MCP stdio sem dependências npm.
- `git-hooks/`: hooks dos vaults (wrapper `sh` + `pre_commit.py`).
- `.githooks/`: hooks deste repositório (barreira de privacidade e testes).
- `agent-hooks/`: hooks de ciclo de vida do Gemini/Antigravity.
- `install.py`: instalação em Linux, macOS e Windows (`install.sh` e `install.ps1` só chamam ele).
- `tests/run_tests.py`: testes em diretórios temporários.
- `tools/privacy_gate.py`: barreira de privacidade.

## Regras

1. Compatível com Linux, macOS e Windows. Use `pathlib`, `sys.executable` para chamar outras ferramentas e nada de `python3` fixo, `readlink -f`, `base64 -w0` ou caminhos `/`-only. Scripts novos são Python.
2. Ferramenta nova ou comportamento novo vem com teste em `tests/run_tests.py`.
3. Antes de comitar: `python3 tests/run_tests.py` e `python3 tools/privacy_gate.py` sem falhas. Os hooks de `.githooks/` rodam os dois, e o `install.py` ativa esses hooks.
4. Exemplos em código e docs usam valores fictícios (`app-prod-01`, `Org A`, `usuario@example.com`). Uma linha que precisa de dado com cara de real, como um padrão de regex, leva o marcador `privacy-gate: allow`.
5. **Só o mantenedor comita aqui.** O hook `lib/maintainer_gate.sh` bloqueia commit e push em clone sem `git config obsidian-config.maintainer true`. Agente de outro usuário não altera nem comita neste repositório: entrega o problema e o patch (`git diff` salvo fora do repo) ao operador, que repassa ao mantenedor. Nunca `--no-verify`. Commit local do mantenedor sim. **Push só com aprovação explícita do dono do repositório.** O GitHub não permite apagar um pull request nem os commits ligados a ele, então dado vazado em push público não tem volta.
6. Mudança no formato de `.vault/config.json`: campo novo com default em `lib/vaultcfg.py` (`DEFAULTS`), documentado no `README.md` e em `config.example.json`. Vaults existentes não podem quebrar.
