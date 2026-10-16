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


def load(vault=None):
    vdir = vault_dir(vault)
    cfg_file = vdir / ".vault" / "config.json"
    data = {}
    if cfg_file.is_file():
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
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


def journal_file(cfg, date_str):
    j = cfg["journal"]
    base = Path(cfg["vault_dir"]) / j["dir"]
    if j.get("per_author"):
        base = base / author(cfg)
    return base / f"{date_str}.md"


def next_change_id(cfg, date_str):
    year_dir = Path(cfg["vault_dir"]) / "08 - Changes" / date_str[:4]
    prefix = f"CHG-{date_str}-" + (f"{author(cfg)}-" if cfg.get("change_id_author") else "")
    seq = 0
    if year_dir.is_dir():
        for f in year_dir.iterdir():
            if f.name.startswith(prefix):
                m = re.match(r"(\d{3})", f.name[len(prefix):])
                if m:
                    seq = max(seq, int(m.group(1)))
    return f"{prefix}{seq + 1:03d}", year_dir


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


def shared_mount_paths(cfg):
    return [m["path"] if isinstance(m, dict) else m for m in cfg.get("shared_mounts", [])]


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
