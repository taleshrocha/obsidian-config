#!/usr/bin/env python3
"""
obsidian-config: desfaz o que o install.py configurou na máquina. Linux, macOS e Windows.

Remove:
  - ferramentas em ~/.local/bin (symlinks ou shims .cmd) que apontam para este repositório;
  - servidores MCP dos vaults (Claude Code, Codex, Gemini), pelo nome de cada vault;
  - o bloco gerenciado das instruções globais (o arquivo some se só tinha o bloco);
  - as skills que vieram deste repositório;
  - hooks e schemas do Gemini/Antigravity instalados por ele;
  - ~/.config/obsidian-config (ponteiro do vault, guards locais);
  - core.hooksPath do vault e dos vaults montados, quando aponta para este repositório.

Não remove o conteúdo dos vaults, o app Obsidian nem o próprio repositório.

Uso: python3 uninstall.py [--vault CAMINHO] [--dry-run]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402

HOME = Path.home()
BLOCK = re.compile(r"\n?<!-- obsidian-config:begin -->.*?<!-- obsidian-config:end -->\n?", re.S)
DRY = False


def act(desc, fn=None):
    print(f"  - {desc}")
    if not DRY and fn:
        fn()


def rm(path):
    p = Path(path)
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


def points_here(p):
    try:
        if p.is_symlink():
            target = os.readlink(p)
            # aponta para este repo, ou é link órfão de uma instalação antiga do obsidian-config
            return str(REPO) in target or ("obsidian-config" in target and not p.exists())
        if p.suffix == ".cmd" and p.is_file():
            return str(REPO) in p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass
    return False


def server_names(vault):
    names = {}
    if vault and (vault / ".vault" / "config.json").is_file():
        cfg = vaultcfg.load(vault)
        names[cfg.get("mcp_name", "obsidian-vault")] = vault
        for mp in vaultcfg.shared_mount_paths(cfg):
            m = vault / mp
            if (m / ".vault" / "config.json").is_file():
                names[vaultcfg.load(m).get("mcp_name") or vaultcfg.slugify(m.name)] = m
    names.setdefault("obsidian-vault", vault)
    return names


def main():
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    DRY = a.dry_run
    vault = None
    if a.vault:
        vault = Path(a.vault).expanduser().resolve()
    elif vaultcfg.USER_CONFIG.is_file():
        try:
            vault = Path(json.loads(vaultcfg.USER_CONFIG.read_text(encoding="utf-8"))["vault"])
        except (ValueError, KeyError):
            vault = None
    print(f"obsidian-config: {REPO}\nVault: {vault or '(desconhecido)'}{'  [dry-run]' if DRY else ''}")
    names = server_names(vault)

    print("\n[1/7] Ferramentas no PATH")
    for d in (HOME / ".local" / "bin", HOME / "bin"):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if points_here(p):
                    act(f"{p}", lambda p=p: rm(p))

    print("\n[2/7] MCP")
    claude = shutil.which("claude")
    for name in names:
        if claude:
            for scope in ("user", "local"):
                act(f"claude mcp remove {name} --scope {scope}",
                    lambda n=name, s=scope: subprocess.run([claude, "mcp", "remove", n, "--scope", s],
                                                          capture_output=True, cwd=str(vault) if vault and vault.exists() else None))
    cj = HOME / ".claude.json"
    if cj.is_file():
        def clean_claude():
            d = json.loads(cj.read_text(encoding="utf-8"))
            for n in names:
                d.get("mcpServers", {}).pop(n, None)
                for proj in d.get("projects", {}).values():
                    proj.get("mcpServers", {}).pop(n, None)
            cj.write_text(json.dumps(d, indent=2), encoding="utf-8")
        act("~/.claude.json: entradas restantes", clean_claude)
    toml = HOME / ".codex" / "config.toml"
    if toml.is_file():
        def clean_codex():
            t = toml.read_text(encoding="utf-8")
            for n in names:
                e = re.escape(n)
                t = re.sub(r"\n?\[mcp_servers\." + e + r"\][\s\S]*?(?=\n\[(?!mcp_servers\." + e + r"[\].])|\Z)", "", t)
            toml.write_text(t, encoding="utf-8")
        act("~/.codex/config.toml", clean_codex)
    for p in (HOME / ".gemini/config/mcp_config.json", HOME / ".gemini/antigravity/mcp_config.json",
              HOME / ".gemini/antigravity-cli/mcp_config.json", HOME / ".gemini/settings.json"):
        if p.is_file():
            def clean_gemini(p=p):
                d = json.loads(p.read_text(encoding="utf-8"))
                for n in names:
                    d.get("mcpServers", {}).pop(n, None)
                p.write_text(json.dumps(d, indent=2), encoding="utf-8")
            act(str(p), clean_gemini)

    print("\n[3/7] Instruções globais (bloco gerenciado)")
    for f in (".claude/CLAUDE.md", ".gemini/GEMINI.md", ".gemini/config/GEMINI.md", ".codex/AGENTS.md"):
        p = HOME / f
        if p.is_file() and "obsidian-config:begin" in p.read_text(encoding="utf-8"):
            def strip(p=p):
                rest = BLOCK.sub("\n", p.read_text(encoding="utf-8")).strip()
                p.unlink() if not rest else p.write_text(rest + "\n", encoding="utf-8")
            act(f"~/{f}", strip)

    print("\n[4/7] Skills")
    for d in (".claude/skills", ".codex/skills", ".gemini/config/skills"):
        for sk in (REPO / "skills").iterdir():
            p = HOME / d / sk.name
            if p.exists() or p.is_symlink():
                act(f"~/{d}/{sk.name}", lambda p=p: rm(p))

    print("\n[5/7] Gemini / Antigravity")
    hooks = HOME / ".gemini/config/hooks.json"
    if hooks.is_file():
        def clean_hooks():
            d = json.loads(hooks.read_text(encoding="utf-8"))
            d.pop("obsidian-vault-lifecycle", None)
            hooks.unlink() if not d else hooks.write_text(json.dumps(d, indent=2), encoding="utf-8")
        act("~/.gemini/config/hooks.json", clean_hooks)
    schemas = HOME / ".gemini/antigravity/mcp/obsidian-vault"
    if schemas.exists():
        act(str(schemas), lambda: rm(schemas))

    print("\n[6/7] Git hooks dos vaults")
    for v in names.values():
        if v and (v / ".git").exists():
            cur = subprocess.run(["git", "-C", str(v), "config", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
            if str(REPO) in cur:
                act(f"core.hooksPath em {v}", lambda v=v: subprocess.run(["git", "-C", str(v), "config", "--unset", "core.hooksPath"]))

    print("\n[7/7] Configuração do usuário")
    if vaultcfg.USER_CONFIG.parent.exists():
        act(str(vaultcfg.USER_CONFIG.parent), lambda: rm(vaultcfg.USER_CONFIG.parent))
    print("\nPronto." + (" Nada foi alterado (--dry-run)." if DRY else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
