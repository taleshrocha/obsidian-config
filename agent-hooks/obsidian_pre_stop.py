#!/usr/bin/env python3
"""
obsidian_pre_stop.py: Lifecycle Stop Hook for Antigravity

Executa antes do agente encerrar a execução.
1. Se houver alterações no vault do Obsidian:
   - Valida a integridade (vault-validate). Se inválido, bloqueia o encerramento.
   - Se válido, faz git add -A, commit e push (remote/branch do config) automaticamente.
2. Se houver alterações não comitadas em repositórios de workspace ativos:
   - Bloqueia o encerramento exigindo que o agente commite e pushe as modificações.
"""

import sys
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402


def sync_vault(vault_dir: Path):
    # 1. Auto-sync AI agents (Gemini, Claude, Codex) FIRST
    sync_agents_bin = REPO / "bin" / "sync-agents"

    if sync_agents_bin.is_file() and os.access(sync_agents_bin, os.X_OK):
        subprocess.run([sys.executable, str(sync_agents_bin), "--quiet"], capture_output=True, text=True, timeout=15)

    # 2. Validate vault integrity
    validator_bin = REPO / "bin" / "vault-validate"

    if validator_bin.is_file() and os.access(validator_bin, os.X_OK):
        res = subprocess.run(
            [sys.executable, str(validator_bin), str(vault_dir)],
            capture_output=True,
            text=True,
            timeout=20
        )
        if res.returncode != 0:
            err_summary = res.stdout.strip() or res.stderr.strip()
            return False, f"A integridade do Obsidian Work Vault falhou na validação pré-parada. Corrija os erros antes de concluir:\n{err_summary}"

    # Stage changes
    subprocess.run(["git", "-C", str(vault_dir), "add", "-A"], capture_output=True, text=True, timeout=10)

    # Check what was staged
    diff_res = subprocess.run(
        ["git", "-C", str(vault_dir), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        timeout=5
    )
    files = [f for f in diff_res.stdout.splitlines() if f.strip()]
    if files:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"docs(vault): auto-sync {len(files)} file(s) ({now_str})"
        c_res = subprocess.run(
            ["git", "-C", str(vault_dir), "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            timeout=15
        )
        if c_res.returncode == 0:
            subprocess.run(
                ["git", "-C", str(vault_dir), "push", CFG["git"]["remote"], CFG["git"]["branch"]],
                capture_output=True,
                text=True,
                timeout=30
            )

    return True, ""

CFG = vaultcfg.load()
SHARED_MOUNTS = vaultcfg.shared_mount_paths(CFG)


def https_auth_args(remote_url):
    """Header HTTPS dinâmico para remotes configurados em git_https_auth (token lido do disco, nunca gravado)."""
    import base64
    for rule in CFG.get("git_https_auth", []):
        token_file = Path(rule.get("token_file", "")).expanduser()
        if rule.get("host_contains") and rule["host_contains"] in remote_url and token_file.is_file():
            tok = token_file.read_text().strip()
            user = rule.get("user", "oauth2")
            hdr = "Authorization: Basic " + base64.b64encode(f"{user}:{tok}".encode()).decode()
            return ["-c", f"http.extraheader={hdr}"]
    return []

def sync_shared_vaults(vault_dir: Path):
    """Valida e comita vaults compartilhados montados como subpasta (repos git próprios).
    Push só quando o repo tem remote 'origin'."""
    for mount in SHARED_MOUNTS:
        shared = vault_dir / mount
        if not (shared / ".git").exists():
            continue
        status = subprocess.run(["git", "-C", str(shared), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=5)
        if not status.stdout.strip():
            continue
        validator = REPO / "bin" / "vault-validate"
        if (shared / ".vault" / "config.json").is_file():
            env_m = dict(os.environ, OBSIDIAN_VAULT_PATH=str(shared))
            res = subprocess.run([sys.executable, str(validator), str(shared)], env=env_m,
                                 capture_output=True, text=True, timeout=20)
            if res.returncode != 0:
                summary = res.stdout.strip() or res.stderr.strip()
                return False, f"O vault compartilhado `{mount}` falhou na validação. Corrija antes de concluir:\n{summary}"
        guard = REPO / "bin" / "shared-vault-guard"
        if guard.is_file():
            res = subprocess.run([sys.executable, str(guard), str(shared)], capture_output=True, text=True, timeout=20)
            if res.returncode != 0:
                return False, f"Conteúdo do vault pessoal vazou para `{mount}`. Remova antes de concluir:\n{res.stdout.strip()}"
        subprocess.run(["git", "-C", str(shared), "add", "-A"], capture_output=True, text=True, timeout=10)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        c_res = subprocess.run(["git", "-C", str(shared), "commit", "-m", f"docs: sincroniza vault do time ({now_str})"],
                               capture_output=True, text=True, timeout=15)
        remote = subprocess.run(["git", "-C", str(shared), "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=5)
        if c_res.returncode == 0 and remote.returncode == 0:
            auth = https_auth_args(remote.stdout)
            subprocess.run(["git", "-C", str(shared), *auth, "pull", "--rebase"], capture_output=True, text=True, timeout=30)
            subprocess.run(["git", "-C", str(shared), *auth, "push"], capture_output=True, text=True, timeout=30)
    return True, ""

def check_workspace_repos(workspace_paths, vault_dir: Path):
    for wp in workspace_paths:
        p = Path(wp)
        if not p.is_dir() or p.resolve() == vault_dir.resolve():
            continue

        # Check if this directory is inside a git repo
        git_check = subprocess.run(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if git_check.returncode == 0:
            repo_root = git_check.stdout.strip()
            if repo_root == str(vault_dir.resolve()):
                continue

            # Check for dirty working tree
            status_res = subprocess.run(
                ["git", "-C", repo_root, "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if status_res.stdout.strip():
                return False, (
                    f"Existem alterações não comitadas no repositório `{repo_root}`.\n"
                    f"Conforme a política obrigatória da estação de trabalho, você DEVE commitar e pushar todas as modificações realizadas antes de encerrar.\n"
                    f"Por favor, execute `git status`, `git add`, `git commit` com mensagem semântica e `git push` agora."
                )

    return True, ""

def main():
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        payload = {}

    vault_dir = Path(CFG["vault_dir"])

    # 1. Sync Obsidian Vault if it has changes
    if vault_dir.is_dir():
        try:
            git_status = subprocess.run(
                ["git", "-C", str(vault_dir), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5
            )
            has_vault_changes = bool(git_status.stdout.strip())
        except Exception:
            has_vault_changes = False

        if has_vault_changes:
            ok, err = sync_vault(vault_dir)
            if not ok:
                print(json.dumps({
                    "decision": "continue",
                    "reason": err
                }))
                return

    # 1b. Sync shared vaults mounted inside the personal vault
    if vault_dir.is_dir():
        ok, err = sync_shared_vaults(vault_dir)
        if not ok:
            print(json.dumps({"decision": "continue", "reason": err}))
            return

    # 2. Check workspace repositories
    workspace_paths = payload.get("workspacePaths", [])
    cwd = os.getcwd()
    if cwd and cwd not in workspace_paths:
        workspace_paths.append(cwd)

    ok, err = check_workspace_repos(workspace_paths, vault_dir)
    if not ok:
        print(json.dumps({
            "decision": "continue",
            "reason": err
        }))
        return

    print(json.dumps({}))

if __name__ == "__main__":
    main()
