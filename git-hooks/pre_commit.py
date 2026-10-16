#!/usr/bin/env python3
"""
Pre-commit de vaults Obsidian configurados pelo obsidian-config.

1. generate_agent_files=true: regenera CLAUDE.md, GEMINI.md e AGENTS.md quando a política
   ou as regras privadas mudam, ou quando estão dessincronizados.
2. Roda bin/vault-validate com a config do próprio vault (.vault/config.json).
3. Roda verificações locais do dev em ~/.config/obsidian-config/pre-commit.d/<vault_name>/
   (ex.: guard contra vazamento do vault pessoal). Nada disso é versionado no vault.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def main():
    root = Path(git("rev-parse", "--show-toplevel").stdout.strip() or os.getcwd())
    os.environ["OBSIDIAN_VAULT_PATH"] = str(root)
    cfg = vaultcfg.load(root)
    py = [sys.executable, "-X", "utf8"]

    if cfg.get("generate_agent_files", True):
        staged = git("diff", "--cached", "--name-only").stdout
        rules = (Path(cfg["policy_note"]).name, Path(cfg["agent_rules_note"]).name)
        out_of_sync = subprocess.call([*py, str(REPO / "bin" / "sync-agents"), "--check-vault-only", "--quiet"]) != 0
        if any(r in staged for r in rules) or out_of_sync:
            print("[pre-commit] Regenerando instruções dos agentes...")
            subprocess.call([*py, str(REPO / "bin" / "sync-agents"), "--quiet"])
            git("add", "CLAUDE.md", "GEMINI.md", "AGENTS.md")

    if (cfg.get("layout") or {}).get("people_dir"):
        subprocess.call([*py, str(REPO / "bin" / "vault"), "people", "sync", "--staged"])

    print("[pre-commit] Validando o vault...")
    if subprocess.call([*py, str(REPO / "bin" / "vault-validate"), str(root)]) != 0:
        print("\n[pre-commit] Commit abortado: validação do vault falhou.")
        return 1

    local = vaultcfg.USER_CONFIG.parent / "pre-commit.d" / vaultcfg.slugify(cfg["vault_name"])
    if local.is_dir():
        for hook in sorted(local.iterdir()):
            if hook.suffix == ".py":
                rc = subprocess.call([*py, str(hook), str(root)])
            elif os.access(hook, os.X_OK):
                rc = subprocess.call([str(hook), str(root)])
            else:
                continue
            if rc != 0:
                print(f"\n[pre-commit] Commit abortado por {hook}.")
                return 1
    print("[pre-commit] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
