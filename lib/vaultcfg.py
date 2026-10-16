"""
vaultcfg: resolve o vault e carrega a configuração privada dele.

Ordem para achar o vault:
  1. variável OBSIDIAN_VAULT_PATH
  2. ~/.config/obsidian-config/config.json  -> {"vault": "/caminho/do/vault"} (gravado pelo install.sh)

Configuração do vault (privada, versionada junto do conteúdo): <vault>/.vault/config.json.
Campos ausentes usam DEFAULTS.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Windows: chamadas diretas (sem -X utf8) ainda imprimem em UTF-8.
if os.name == "nt" and not sys.flags.utf8_mode:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obsidian-config" / "config.json"
REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "vault_name": "Work",
    "organizations": [],
    "expected_dirs": [
        "00 - Dashboard", "01 - Organizations", "02 - Projects", "03 - Repositories",
        "04 - Servers", "05 - Services", "06 - Applications", "07 - Infrastructure",
        "08 - Changes", "09 - Incidents", "10 - Procedures", "11 - Architecture",
        "12 - Decisions", "13 - Meetings", "14 - Research", "15 - People",
        "16 - Tools", "90 - Files", "99 - Templates",
    ],
    "allowed_root_entries": [".git", ".gitignore", ".gitattributes", ".obsidian", ".vault", ".obsidian-config", ".mirrors", ".trash"],
    # Vaults de time montados como subpasta. Convenção: todos dentro de "80 - Shared Vaults/",
    # um por projeto (ex.: "80 - Shared Vaults/Time A"), com a pasta no .gitignore do vault.
    "shared_mounts": [],
    "projects_dir": "~/Projects",
    "policy_note": "07 - Infrastructure/AI/Shared Agent Policy.md",
    "agent_rules_note": "07 - Infrastructure/AI/Agent Rules.md",
    "policy_topics": [],
    "git": {"remote": "origin", "branch": "main", "auto_push": True},
    "git_https_auth": [],
    # Organização do conteúdo (vaults de time). org_subfolders: None = só quando há mais de uma
    # organização; date_folders: pastas que ganham AAAA/MM (ex.: "08 - Changes"); people_dir: pasta
    # com uma nota por pessoa do time (ligada ao autor por `author:`), vazio desliga;
    # people_aliases: {"slug-do-autor": "Nome da nota"} quando o slug do git não bate com o nome;
    # people_suffix: nota "Nome (Org)", para o link não colidir com a mesma pessoa em outro vault
    # montado junto (None = ligado quando o vault tem uma só organização).
    "layout": {"org_subfolders": None, "date_folders": [], "people_dir": "", "people_aliases": {}, "people_suffix": None},
    # Snapshot das configs de ~/.claude, ~/.gemini, ~/.agent(s), ~/.codex: {enabled, dest, keep, max_file_kb, include}.
    "agent_backup": {},
    "default_change_server": "",
    "guard": {"allow": [], "common_org_words": []},
    # Vault de time: IDs de change com autor e diário por autor evitam colisão entre devs.
    "change_id_author": False,
    "journal": {"dir": "13 - Meetings", "per_author": False, "type": "meeting"},
    # Checagens de privacidade (e-mail, telefone, home, senha literal, Dataview sem escopo).
    "privacy_checks": False,
    # Contas de servidor cujo /home/<conta> pode aparecer (ex.: ["nginx", "deploy"]).
    "privacy_allow_home_users": [],
    # Notas isentas das checagens de privacidade e segredo, por decisão explícita do time
    # (ex.: uma nota de credenciais de ambientes de teste). Use o mínimo possível.
    "privacy_exempt_paths": [],
    # Gera CLAUDE.md/GEMINI.md/AGENTS.md na raiz a partir da base + regras privadas.
    # Vault de time mantém o próprio AGENTS.md: use false.
    "generate_agent_files": True,
    # Repositório compartilhado (vault de time): o install não escreve config do Obsidian,
    # templates nem notas de política dentro dele; só baixa plugins (ignorados pelo git).
    "shared_repo": False,
    # Nome do servidor MCP deste vault quando montado dentro de outro.
    "mcp_name": "obsidian-vault",
}


def _merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def vault_dir(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("OBSIDIAN_VAULT_PATH") or os.environ.get("VAULT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if USER_CONFIG.is_file():
        try:
            v = json.loads(USER_CONFIG.read_text(encoding="utf-8")).get("vault")
            if v:
                return Path(v).expanduser().resolve()
        except (OSError, ValueError):
            pass
    sys.stderr.write("Vault não configurado. Rode install.sh --vault <caminho> ou exporte OBSIDIAN_VAULT_PATH.\n")
    sys.exit(2)


def _host_mounts(vdir):
    """True quando vdir é um shared_mount declarado no config de um vault acima dele."""
    for parent in vdir.parents:
        f = parent / ".vault" / "config.json"
        if f.is_file():
            try:
                host = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return False
            mounts = [m["path"] if isinstance(m, dict) else m for m in host.get("shared_mounts", [])]
            return any((parent / m).resolve() == vdir for m in mounts)
    return False


def _unsafe_rel(p):
    parts = Path(str(p)).parts
    return not p or Path(str(p)).is_absolute() or ".." in parts or parts[0].startswith(".")


def sanitize_team_config(data):
    """Config de vault de time vem de um repositório que outros editam. Campos que mudam o
    comportamento da máquina local (arquivo de token, variável de ambiente, destino do backup)
    e pastas que saem do vault são descartados."""
    data = dict(data)
    data.pop("agent_backup", None)
    data["git_https_auth"] = [{k: v for k, v in r.items() if k not in ("token_file", "token_env")}
                              for r in data.get("git_https_auth", []) if isinstance(r, dict)]
    journal = dict(data.get("journal") or {})
    if "dir" in journal and _unsafe_rel(journal["dir"]):
        journal.pop("dir")
    data["journal"] = journal
    layout = dict(data.get("layout") or {})
    if "people_dir" in layout and layout["people_dir"] and _unsafe_rel(layout["people_dir"]):
        layout["people_dir"] = ""
    layout["date_folders"] = [d for d in layout.get("date_folders", []) if not _unsafe_rel(d)]
    data["layout"] = layout
    for key in ("policy_note", "agent_rules_note"):
        if key in data and _unsafe_rel(data[key]):
            data.pop(key)
    return data


def load(vault=None):
    vdir = vault_dir(vault)
    cfg_file = vdir / ".vault" / "config.json"
    data = {}
    if cfg_file.is_file():
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
    if data.get("shared_repo") or _host_mounts(vdir):
        data = sanitize_team_config(data)
    cfg = _merge(DEFAULTS, data)
    cfg["vault_dir"] = vdir
    cfg["projects_dir"] = str(Path(cfg["projects_dir"]).expanduser())
    return cfg


def slugify(text):
    import unicodedata
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def author(cfg):
    """Slug do autor: VAULT_AUTHOR ou git config user.name do vault."""
    if os.environ.get("VAULT_AUTHOR"):
        return slugify(os.environ["VAULT_AUTHOR"])
    try:
        name = subprocess.run(["git", "-C", str(cfg["vault_dir"]), "config", "user.name"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return slugify(name) or "unknown"


def real_orgs(cfg):
    return [o for o in organizations(cfg) if o.lower() != "cross-organization"]


def org_subfolders(cfg):
    """Pastas por organização dentro de 03, 04, 14...: só fazem sentido com mais de uma organização."""
    flag = cfg.get("layout", {}).get("org_subfolders")
    return len(real_orgs(cfg)) > 1 if flag is None else bool(flag)


def default_org(cfg):
    orgs = real_orgs(cfg)
    return orgs[0] if len(orgs) == 1 else "Cross-Organization"


def date_sub(cfg, folder, date_str):
    """'AAAA/MM' quando a pasta usa subpastas de data, senão ''."""
    return f"{date_str[:4]}/{date_str[5:7]}" if folder in cfg.get("layout", {}).get("date_folders", []) else ""


def people_dir(cfg):
    d = cfg.get("layout", {}).get("people_dir", "")
    return Path(cfg["vault_dir"]) / d if d else None


def _frontmatter_field(text, key):
    m = re.search(r"(?s)\A---\r?\n(.*?)\r?\n---", text)
    if not m:
        return ""
    f = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*)$", m.group(1))
    return f.group(1).strip().strip("'\"") if f else ""


def _frontmatter_list(text, key):
    """Valores de uma propriedade lista (`key: [a, b]` ou itens `- a`) ou texto simples."""
    m = re.search(r"(?s)\A---\r?\n(.*?)\r?\n---", text)
    if not m:
        return []
    km = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*)$", m.group(1))
    if not km:
        return []
    inline = km.group(1).strip()
    if inline:
        return [v.strip().strip("'\"") for v in inline.strip("[]").split(",") if v.strip()]
    block = re.match(r"(?:\n[ \t]+-[^\n]*)*", m.group(1)[km.end():]).group(0)
    return [l.split("-", 1)[1].strip().strip("'\"") for l in block.splitlines() if l.strip()]


def _strip_suffix(stem):
    return re.sub(r"\s*\([^()]*\)\s*$", "", stem)


def people_suffix(cfg):
    flag = cfg.get("layout", {}).get("people_suffix")
    return len(real_orgs(cfg)) == 1 if flag is None else bool(flag)


def person_stem(cfg, name):
    """Nome do arquivo da nota de pessoa: 'Nome (Org)' quando o sufixo está ligado."""
    return f"{name} ({real_orgs(cfg)[0]})" if people_suffix(cfg) and real_orgs(cfg) else name


def person_display(path):
    """Nome da pessoa sem o sufixo de organização: campo `name` ou o arquivo."""
    return _frontmatter_field(Path(path).read_text(encoding="utf-8", errors="replace"), "name") or _strip_suffix(Path(path).stem)


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", slugify(text))


def find_person(cfg, slug):
    """Nota de pessoa de um autor do git. O nome no git pode diferir do nome da nota, então vale,
    nesta ordem: alias na config, `author:` ou `git_authors:` da nota, nome igual ignorando
    espaços e hífens ("Maria Souza" = "mariasouza"). Devolve o Path ou None."""
    d = people_dir(cfg)
    if not d or not d.is_dir():
        return None
    slug = slugify(slug)
    alias = cfg.get("layout", {}).get("people_aliases", {}).get(slug)
    if alias and (d / f"{alias}.md").is_file():
        return d / f"{alias}.md"
    notes = []
    for f in sorted(d.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if _frontmatter_field(text, "type") == "person":
            notes.append((f, text))
    for f, text in notes:
        ids = [_frontmatter_field(text, "author"), *_frontmatter_list(text, "git_authors")]
        if slug in {slugify(i) for i in ids if i}:
            return f
    for f, text in notes:
        if _norm(_strip_suffix(f.stem)) == _norm(slug) or _norm(_frontmatter_field(text, "name")) == _norm(slug):
            return f
    return None


def display_name(cfg):
    if os.environ.get("VAULT_AUTHOR"):
        return os.environ["VAULT_AUTHOR"].strip()
    try:
        return subprocess.run(["git", "-C", str(cfg["vault_dir"]), "config", "user.name"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or author(cfg)
    except (OSError, subprocess.SubprocessError):
        return author(cfg)


def person_note_text(cfg, name, slug, body="", role=""):
    from datetime import date
    orgs = real_orgs(cfg)
    body = body.strip() or "Resumo da atuação e das responsabilidades da pessoa no time."
    return (f"---\ntype: person\nname: {name}\norganization: {orgs[0] if orgs else ''}\nauthor: {slug}\n"
            f"role: {role}\nstatus: active\nlast_verified: {date.today().isoformat()}\n---\n\n# {name}\n\n"
            f"## Visão Geral\n\n{body}\n\n## Identificadores\n\n"
            f"- **Nome no git:** `{slug}`. Outros nomes do mesmo autor entram em `git_authors:` no frontmatter.\n"
            f"- **Pasta do diário:** `{(cfg.get('journal') or {}).get('dir', '')}/{name}/`\n\n"
            "## Documentos Relacionados\n\n"
            "Changes, diários e notas que citam esta pessoa aparecem no painel de backlinks do Obsidian.\n")


def ensure_person_note(cfg):
    """Garante a nota de pessoa do autor atual em people_dir. Devolve o Path (None se desligado)."""
    d = people_dir(cfg)
    if not d:
        return None
    slug = author(cfg)
    found = find_person(cfg, slug)
    if found:
        return found
    name = re.sub(r'[/\\?%*:|"<>]', "-", display_name(cfg)).strip() or slug
    d.mkdir(parents=True, exist_ok=True)
    note = d / f"{person_stem(cfg, name)}.md"
    if not note.exists():
        note.write_text(person_note_text(cfg, name, slug), encoding="utf-8")
    return note


def ensure_person(cfg):
    """Nome da nota (usado nos links) do autor atual; '' se desligado."""
    note = ensure_person_note(cfg)
    return note.stem if note else ""


def person_dirname(cfg):
    """Nome da pessoa sem sufixo (pasta do diário e título); '' se desligado."""
    note = ensure_person_note(cfg)
    return person_display(note) if note else ""


def author_link(cfg):
    name = ensure_person(cfg)
    return f"[[{name}]]" if name else ""


def journal_file(cfg, date_str):
    j = cfg["journal"]
    base = Path(cfg["vault_dir"]) / j["dir"]
    if j.get("per_author"):
        base = base / (person_dirname(cfg) or author(cfg))  # pasta com o nome da pessoa, não o slug do git
    sub = date_sub(cfg, j["dir"], date_str)
    return (base / sub if sub else base) / f"{date_str}.md"


def next_change_id(cfg, date_str):
    sub = date_sub(cfg, "08 - Changes", date_str) or date_str[:4]
    year_dir = Path(cfg["vault_dir"]) / "08 - Changes" / sub
    prefix = f"CHG-{date_str}-" + (f"{author(cfg)}-" if cfg.get("change_id_author") else "")
    seq = 0
    if year_dir.is_dir():
        for f in year_dir.iterdir():
            if f.name.startswith(prefix):
                m = re.match(r"(\d{3})", f.name[len(prefix):])
                if m:
                    seq = max(seq, int(m.group(1)))
    return f"{prefix}{seq + 1:03d}", year_dir


def shared_mount_paths(cfg):
    return [m["path"] if isinstance(m, dict) else m for m in cfg.get("shared_mounts", [])]


def _credential_helper_token(remote_url, user="oauth2"):
    """Token do gerenciador de credenciais do git (Git Credential Manager, Keychain, libsecret).
    Nunca abre prompt: sem credencial guardada, devolve None."""
    from urllib.parse import urlparse
    u = urlparse(remote_url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    query = f"protocol={u.scheme}\nhost={u.netloc.rsplit('@', 1)[-1]}\nusername={user}\n\n"
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        res = subprocess.run(["git", "credential", "fill"], input=query, capture_output=True, text=True,
                             timeout=15, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip() or None
    return None


def resolve_token(rule, remote_url):
    """Token de uma regra git_https_auth. Ordem: variável de ambiente (token_env),
    arquivo (token_file), gerenciador de credenciais do git. O caminho do arquivo
    nunca é suposto: cada máquina escolhe o seu."""
    env_name = rule.get("token_env")
    if env_name and os.environ.get(env_name, "").strip():
        return os.environ[env_name].strip()
    if rule.get("token_file"):
        f = Path(rule["token_file"]).expanduser()
        if f.is_file():
            tok = f.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    return _credential_helper_token(remote_url, rule.get("user", "oauth2"))


def https_auth_args(cfg, remote_url, extra_rules=()):
    """Argumentos `-c http.extraheader=...` para o remote, ou [] quando não há token.
    Sem header, o git ainda usa o credential helper da máquina por conta própria."""
    import base64
    for rule in [*cfg.get("git_https_auth", []), *extra_rules]:
        host = rule.get("host_contains")
        if not host or host not in remote_url:
            continue
        tok = resolve_token(rule, remote_url)
        if tok:
            basic = base64.b64encode(f"{rule.get('user', 'oauth2')}:{tok}".encode()).decode()
            return ["-c", f"http.extraheader=Authorization: Basic {basic}"]
    return []


def store_credential(remote_url, token, user="oauth2"):
    """Guarda o token no gerenciador de credenciais do git (cofre do sistema)."""
    from urllib.parse import urlparse
    u = urlparse(remote_url.strip())
    payload = f"protocol={u.scheme}\nhost={u.netloc.rsplit('@', 1)[-1]}\nusername={user}\npassword={token}\n\n"
    res = subprocess.run(["git", "credential", "approve"], input=payload, capture_output=True, text=True, timeout=15)
    return res.returncode == 0




def organizations(cfg):
    """Organizações: config explícita ou notas em 01 - Organizations."""
    if cfg.get("organizations"):
        return list(cfg["organizations"])
    org_dir = Path(cfg["vault_dir"]) / "01 - Organizations"
    return sorted(p.stem for p in org_dir.glob("*.md")) if org_dir.is_dir() else []


if __name__ == "__main__":
    # Uso em shell: python3 lib/vaultcfg.py vault_dir | <chave>
    c = load()
    key = sys.argv[1] if len(sys.argv) > 1 else "vault_dir"
    val = c.get(key)
    print(json.dumps(val, default=str) if isinstance(val, (list, dict)) else val)
