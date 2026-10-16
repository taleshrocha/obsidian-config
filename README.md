# obsidian-config

Ferramentas e configuração para manter vaults Obsidian como base de conhecimento operacional: servidores, serviços, repositórios, procedimentos, changes e decisões. Os vaults são escritos por humanos e por agentes de IA (Claude Code, Gemini CLI, Codex). Funciona em Linux, macOS e Windows.

Este repositório guarda só configuração e ferramentas. Conteúdo e tudo que é pessoal ficam nos vaults:

| Aqui (público) | No vault (privado) |
|---|---|
| CLI `vault`, validador, auditor de saúde, canvas, guard de vazamento | Notas |
| MCP server | `.vault/config.json`: organizações, mounts, hosts Git, padrões |
| Instruções base dos agentes | Política e regras privadas dos agentes |
| Hooks de Git e de ciclo de vida dos agentes | Templates customizados |
| Templates genéricos, `.obsidian` base, versões de plugins e temas | Estado do Obsidian |

## Instalação

Requisitos: `git`, Python 3.9+, Node 18+ (para o MCP) e Obsidian.

Clone dentro do vault, numa pasta oculta. Assim o agente de IA que trabalha no vault enxerga e melhora as ferramentas. Obsidian, validador e MCP ignoram pastas que começam com ponto. Adicione `.obsidian-config/` ao `.gitignore` do vault.

Linux e macOS:

```bash
git clone https://github.com/taleshrocha/obsidian-config.git ~/Vault/.obsidian-config
~/Vault/.obsidian-config/install.sh --vault ~/Vault
```

Windows (PowerShell):

```powershell
git clone https://github.com/taleshrocha/obsidian-config.git $HOME\Vault\.obsidian-config
& $HOME\Vault\.obsidian-config\install.ps1 --vault $HOME\Vault
```

Opções: `--install-obsidian` instala o app se ele faltar (`.deb` no Debian/Ubuntu, Homebrew no macOS, winget no Windows; `--obsidian-version` fixa a versão), `--skip-extensions` pula o download de plugins e temas, e `--no-agents` não mexe nas configurações dos agentes.

Para desfazer a instalação sem tocar no conteúdo do vault: `python3 uninstall.py` (`--dry-run` mostra o que seria removido).

`install.py` é idempotente:

1. Grava o caminho do vault em `~/.config/obsidian-config/config.json` e cria `<vault>/.vault/config.json` a partir de `config.example.json`, se ainda não existir.
2. Cria pastas da taxonomia e templates ausentes. Arquivos existentes não são alterados.
3. Aplica o `.obsidian` base sem sobrescrever (`--force-obsidian-config` sobrescreve). Baixa plugins e temas nas versões de `obsidian/extensions.json` das releases oficiais (`--skip-extensions` pula) e registra o vault no Obsidian.
4. Coloca as ferramentas em `~/.local/bin`: symlinks no Linux e no macOS, shims `.cmd` no Windows.
5. Aponta `core.hooksPath` do vault, e dos vaults montados, para `git-hooks/`. Ativa a barreira de privacidade deste repositório (`.githooks/`).
6. Instala guards locais fora dos repositórios (ver "Vaults de time").
7. Roda `sync-agents`, que gera as instruções dos agentes e registra um MCP por vault em Claude Code, Gemini CLI e Codex.
8. Valida o vault.

## Taxonomia

Padrão em pt-BR (preset `pt-BR`). O preset `en` mantém os nomes antigos em inglês (`00 - Dashboard`, `08 - Changes`...). Os dois ficam em `lib/folders.json`, lido pelas ferramentas Python e pelo MCP.

| Pasta | Papel | Para que serve |
|---|---|---|
| `00 - Painel` | `dashboard` | Painéis com Dataview; ponto de entrada |
| `01 - Organizacoes` | `organizations` | Uma nota por organização |
| `02 - Projetos` | `projects` | Projetos, escopo, pendências (`- [ ] #todo/...`) |
| `03 - Repositorios` | `repositories` | Um repositório git por nota: stack, comandos, CI |
| `04 - Servidores` | `servers` | Hosts: IP, acesso, ambiente (`environment` obrigatório) |
| `05 - Servicos` | `services` | Serviços e daemons: porta, servidor, dependências |
| `06 - Aplicacoes` | `applications` | Aplicações de negócio e onde rodam |
| `07 - Infraestrutura` | `infrastructure` | Rede, VPN, observabilidade, política dos agentes (`AI/`) |
| `08 - Mudancas/AAAA` | `changes` | Change records `CHG-AAAA-MM-DD-NNN` |
| `09 - Incidentes` | `incidents` | Incidentes e post-mortems |
| `10 - Procedimentos` | `procedures` | Runbooks e procedimentos |
| `11 - Arquitetura` | `architecture` | Diagramas, canvas de topologia, Excalidraw |
| `12 - Decisoes` | `decisions` | ADRs |
| `13 - Reunioes` | `meetings` | Diário e atas (`journal.dir`) |
| `14 - Pesquisa` | `research` | Pesquisas e sínteses de fontes (`vault ingest`) |
| `15 - Pessoas` | `people` | Uma nota por pessoa |
| `16 - Ferramentas` | `tools` | Scripts e ferramentas de uso do desenvolvedor |
| `90 - Arquivos` | `files` | Anexos e fontes brutas imutáveis (`90 - Arquivos/Fontes`) |
| `99 - Modelos` | `templates` | Templates usados por `vault new` e pelo Templater |

`folders` no config troca o preset, renomeia papéis isolados e define `root`, a subpasta onde fica o conteúdo. Com `root: "Pessoal"`, `08 - Mudancas` vira `Pessoal/08 - Mudancas`, e os vaults de time ficam ao lado de `Pessoal/` na raiz. `expected_dirs`, `policy_note`, `agent_rules_note` e `journal.dir` derivam do mapa quando o config não os define. Toda nota tem frontmatter com `type`. Servidores exigem `environment`. Changes exigem `id`, `date`, `status` e `server`, `service` ou `project`.

## `.vault/config.json`

| Campo | Default | Uso |
|---|---|---|
| `vault_name` | `Work` | Nome do vault (também identifica guards locais) |
| `organizations` | `[]` | Organizações. Vazio: lê a pasta de organizações |
| `folders` | `preset: pt-BR`, `root: ""` | Mapa de pastas: `preset` (`pt-BR` ou `en`), `root` e `<papel>: <nome>` para renomear um papel |
| `expected_dirs` | taxonomia acima | Pastas obrigatórias |
| `projects_dir` | `~/Projects` | Onde `vault-health` procura repositórios não catalogados |
| `policy_note` | `<root>/07 - Infraestrutura/AI/Shared Agent Policy.md` | Política. O checksum dela vai nos arquivos gerados |
| `agent_rules_note` | `<root>/07 - Infraestrutura/AI/Agent Rules.md` | Regras privadas anexadas às instruções base (numere a partir de 13) |
| `policy_topics` | `[]` | Seções esperadas na política (só aviso) |
| `generate_agent_files` | `true` | Gera `CLAUDE.md`, `GEMINI.md` e `AGENTS.md`. Vault de time com `AGENTS.md` próprio usa `false` |
| `mcp_name` | `obsidian-vault` | Nome do MCP deste vault |
| `change_id_author` | `false` | IDs `CHG-YYYY-MM-DD-<autor>-NNN` (vault de time) |
| `journal` | `<root>/13 - Reunioes`, sem autor | Diário: `dir`, `per_author`, `type` |
| `shared_repo` | `false` | Vault de time: o install não escreve config do Obsidian, templates nem notas de política no repositório; só baixa plugins |
| `auto_pull` | igual a `shared_repo` | O MCP faz `fetch` + `merge --ff-only` antes de cada ferramenta. Não faz rebase: se houver commit local divergente ou falha de rede, avisa na saída |
| `auto_pull_ttl_seconds` | `300` | Intervalo mínimo entre dois fetches do MCP. `VAULT_AUTO_PULL_TTL_SECONDS` sobrepõe |
| `privacy_checks` | `false` | Bloqueia e-mail, telefone, caminho de home, senha literal e Dataview sem escopo |
| `shared_mounts` | `[]` | Vaults de time montados como subpasta: `{"path", "organization", "roster"}`. Recomendado: `path` na raiz, ao lado de `folders.root` |
| `git` | `origin`/`main`, push automático | Usado por `vault sync` e pelo hook de encerramento |
| `git_https_auth` | `[]` | Header HTTPS por host: `{host_contains, user, token_env?, token_file?}`. Token resolvido por variável de ambiente, arquivo ou cofre do git (`vault auth setup`, guiado). Nunca grava credencial. O MCP de um vault de time usa as regras dele e, se não houver, as do vault pessoal que o monta |
| `layout` | `org_subfolders: null`, `date_folders: []`, `people_dir: ""`, `people_aliases: {}`, `people_suffix: null` | Organização das pastas. `org_subfolders`: pasta por organização em 03, 04, 14 etc., por padrão só com mais de uma organização. `date_folders`: pastas que ganham `AAAA/MM` (ex.: `08 - Mudancas`, `13 - Diario`). `people_dir`: uma nota de pessoa por membro, ligada ao autor por `author:`; changes e diários citam `[[Pessoa]]`. `people_aliases`: slug do git para nome da nota. `people_suffix`: nota `Nome (Org)` para o link não colidir com a mesma pessoa em outro vault montado junto (padrão: ligado com uma só organização). `vault people sync` cria as notas que faltam e preenche `authors:` de cada nota com quem a escreveu, pelo histórico do git; o pre-commit do vault faz o mesmo com o autor do commit. O validador falha se o layout for violado |
| `agent_backup` | `{}` | Snapshot das configs dos agentes: `enabled`, `dest`, `keep` (20), `max_file_kb` (2048), `include` (dir -> globs). Ver `bin/agent-backup` |
| `default_change_server` | `""` | Padrão de `vault change` |
| `guard` | `allow: []`, `common_org_words: []` | Ajustes do guard |

O autor vem de `VAULT_AUTHOR` ou de `git config user.name`.

## Vaults de time

Um vault de time é um repositório próprio com `.vault/config.json` (por exemplo `change_id_author: true`, `journal.per_author: true`, `privacy_checks: true`, `generate_agent_files: false`, `mcp_name`). Ele não carrega cópia de ferramentas. Instalar este repositório é opcional: quem já tem o próprio setup de Obsidian só clona e abre o vault. Quem instala ganha validação no pre-commit, MCP e CLI. Para valer para todos, a CI do vault de time clona este repositório e roda `bin/vault-validate` a cada push.

Quem também tem vault pessoal usa este layout, aberto como um vault só no Obsidian:

```
Work/                    repositório git do vault pessoal; é a pasta aberta no Obsidian
├── .obsidian/           config do Obsidian (vale para os três)
├── .vault/config.json   config pessoal: folders.root = "Pessoal", shared_mounts = ["Time A", "Time B"]
├── .obsidian-config/    clone deste repositório (ignorado pelo git)
├── Pessoal/             conteúdo pessoal, com as pastas numeradas
├── Time A/              vault do time A: repositório git próprio, no .gitignore do pessoal
└── Time B/              vault do time B: idem
```

Cada vault de time é declarado em `shared_mounts` e listado no `.gitignore` do pessoal. Com isso:

- `vault-validate` do vault pessoal valida o mount com a config do próprio mount.
- `sync-agents` registra um MCP para cada vault (`mcp_name` de cada um).
- `shared-vault-guard` gera, a cada execução e só na máquina, uma denylist com nomes, hosts, IPs, IDs e aliases das notas pessoais e das outras organizações. Depois varre o mount. O `install.py` coloca um runner dele em `~/.config/obsidian-config/pre-commit.d/<vault_name>/`, que o pre-commit do vault do time executa. A denylist nunca é gravada em repositório.
- Para um dev sem vault pessoal: `install.py --vault <vault-do-time>`.

### Proteção contra prompt injection

O vault do time é editado por várias pessoas e lido por agentes como contexto e instrução. As ferramentas tratam o conteúdo como dado e limitam o que um agente enganado consegue fazer:

- `vault-validate` reprova conteúdo que o agente lê e o humano não vê: caracteres Unicode de controle bidi e tag, caracteres invisíveis (zero-width, word joiner, BOM fora do início), comentário HTML com texto dirigido a agente ou comando, texto escondido por HTML/CSS e bloco base64 longo. Em `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `99 - Templates/`, `policy_note` e `.vault/config.json` qualquer comentário HTML reprova, exceto os marcadores do bloco gerenciado. Em `90 - Files/Sources/` só bidi e tag reprovam, porque fonte bruta é imutável.
- O MCP devolve o resultado das ferramentas de leitura entre `<vault-data-<nonce>>` e `</vault-data-<nonce>>`, com um nonce aleatório por processo, e troca caractere invisível por `[U+XXXX]`. Leitura fora do vault ou em pasta oculta (`.git`, `.vault`) é recusada.
- As ferramentas de escrita do MCP só gravam `.md` em `08 - Changes/`, na pasta do diário e na pasta de pessoas, recusam symlink e conteúdo acima de 64 KB, e reduzem título, cabeçalho e campos de frontmatter a uma linha. `open_in_gui` chama `obsidian-cli` sem shell.
- Toda chamada de ferramenta do MCP vai para `~/.local/state/obsidian-config/mcp-audit.jsonl` (`$XDG_STATE_HOME`, ou o caminho em `OBSIDIAN_MCP_AUDIT_LOG`), com strings cortadas em 200 caracteres. O arquivo gira em 5 MB.
- Config de vault de time (`shared_repo: true` ou mount declarado no vault pessoal) não define `token_file`, `token_env` nem `agent_backup`, e pastas com `..`, caminho absoluto ou pasta oculta em `journal.dir`, `layout.people_dir`, `layout.date_folders`, `policy_note` e `agent_rules_note` são descartadas. Token e backup vêm só da config da própria máquina.
- O hook de encerramento comita no vault do time só as pastas de conteúdo (`expected_dirs` menos `99 - Templates`). Mudança em qualquer outro caminho (`AGENTS.md`, `.vault/`, `.gitlab-ci.yml`, `.obsidian/`, templates) bloqueia o encerramento até o operador revisar o diff. O hook nunca faz push de vault de time: ele avisa os commits pendentes e o push acontece depois da aprovação do operador.
- `sync-agents` remove comentários HTML da nota de regras privadas antes de gravar as instruções globais.

No servidor Git, proteja a branch principal e exija revisão para `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.vault/` e o arquivo de CI. Essas regras dependem do host e ficam fora deste repositório.

## Política dos agentes

Quem instala o obsidian-config recebe a mesma disciplina de agente, sem escrever nada:

- **`agents/base-instructions.md`:** regras curtas que o `sync-agents` grava em `~/.claude/CLAUDE.md`, `~/.gemini/GEMINI.md` e `~/.codex/AGENTS.md`, dentro de um bloco gerenciado. O que você já tinha nesses arquivos fica preservado.
- **`agents/policy.md`:** a política completa. Ela cobre consulta ao vault antes de agir, funil de leitura para economizar contexto, padrão LLM-Wiki, loop engineering (sucesso observável, parada em caso de oscilação, validação completa), documentação de toda descoberta, segredos, Git, encerramento com push, preferências no vault em vez da memória privada da ferramenta, redação técnica direta (unslop), vaults compartilhados e separação entre config e conteúdo. Claude e Gemini a importam com `@`; para o Codex ela vai embutida.
- **Política local e regras privadas:** o install cria `policy_note` e `agent_rules_note` no vault a partir de `agents/*.template.md`. O que é específico seu vai ali e prevalece sobre a base. Em vault de time, a política local é o `AGENTS.md` do próprio vault.

## Ferramentas

| Comando | Função |
|---|---|
| `vault` | CLI: `status`, `search`, `meta`, `outline`, `section`, `links`, `new`, `change`, `log`, `ingest`, `open`, `canvas`, `health`, `validate`, `sources`, `sync-agents`, `sync` |
| `vault-validate` | Estrutura, frontmatter, links, segredos, privacidade e mounts |
| `vault-health` | Notas órfãs, `last_verified` defasado, repositórios não catalogados |
| `vault-sources` | Fontes brutas pendentes de ingestão e tarefas |
| `vault-semantic-search` | Busca semântica opcional (requer `numpy`) |
| `generate-canvas` | Canvas de topologia por organização |
| `sync-agents` | Instruções, skills e MCP para Claude Code, Gemini CLI e Codex |
| `shared-vault-guard` | Bloqueia vazamento do vault pessoal para vaults de time e para este repositório |

## Contribuir (humanos e agentes)

Leia [AGENTS.md](AGENTS.md). Resumo:

- Mecanismo vem para cá; valor pessoal fica no vault.
- `python3 tests/run_tests.py` e `python3 tools/privacy_gate.py` sem falhas. Os hooks de `.githooks/` rodam os dois no commit e no push.
- `tools/privacy_gate.py` bloqueia caminho de home, e-mail, IP privado, tokens e chaves. Executa também os scripts locais de `~/.config/obsidian-config/privacy.d/`, entre eles o guard com a denylist do vault pessoal.
- A CI roda os testes em Linux, macOS e Windows.

## Licença

Plugins e temas são baixados das releases oficiais e seguem as licenças dos seus autores. Nada de terceiros é redistribuído aqui.
