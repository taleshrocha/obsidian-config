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
    "shared_mounts": [],
    "projects_dir": "~/Projects",
    "policy_note": "07 - Infrastructure/AI/Shared Agent Policy.md",
    "agent_rules_note": "07 - Infrastructure/AI/Agent Rules.md",
    "policy_topics": [],
    "git": {"remote": "origin", "branch": "main", "auto_push": True},
    "git_https_auth": [],
    "default_change_server": "",
    "guard": {"allow": [], "common_org_words": []},
    # Vault de time: IDs de change com autor e diário por autor evitam colisão entre devs.
    "change_id_author": False,
    "journal": {"dir": "13 - Meetings", "per_author": False, "type": "meeting"},
    # Checagens de privacidade (e-mail, telefone, home, senha literal, Dataview sem escopo).
    "privacy_checks": False,
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
