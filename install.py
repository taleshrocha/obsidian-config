#!/usr/bin/env python3
"""
obsidian-config: instala ferramentas, agentes de IA e configuração base do Obsidian
para um vault de conhecimento operacional. Linux, macOS e Windows.

Uso:
  python3 install.py --vault CAMINHO [--skip-extensions] [--force-obsidian-config]
                     [--no-agents] [--personal-vault CAMINHO]

--vault           vault principal desta máquina (pessoal ou de time)
--personal-vault  vault pessoal que monta este vault (habilita o guard de vazamento)

Idempotente. Nada pessoal é gravado neste repositório: a configuração do vault fica em
<vault>/.vault/config.json e o ponteiro do vault em ~/.config/obsidian-config/config.json.
"""
import argparse
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402

TOOLS = ["vault", "vault-validate", "vault-health", "vault-sources", "vault-semantic-search",
         "generate-canvas", "sync-agents", "shared-vault-guard"]
WINDOWS = os.name == "nt"


def say(step, text):
    print(f"\n[{step}] {text}")


def ok(text):
    print(f"  ✓ {text}")


def warn(text):
    print(f"  ! {text}")


def obsidian_app_config():
    """Arquivo global do Obsidian (registro de vaults) por sistema."""
    home = Path.home()
    if WINDOWS:
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "obsidian" / "obsidian.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    for cand in (home / ".config" / "obsidian", home / ".var/app/md.obsidian.Obsidian/config/obsidian",
                 home / "snap/obsidian/current/.config/obsidian"):
        if cand.is_dir():
            return cand / "obsidian.json"
    return home / ".config" / "obsidian" / "obsidian.json"


def bin_dir():
    return Path.home() / ".local" / "bin"


def link_tool(name, target):
    """Disponibiliza a ferramenta no PATH: symlink em POSIX, shim .cmd no Windows."""
    d = bin_dir()
    d.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        (d / f"{name}.cmd").write_text(f'@"{sys.executable}" -X utf8 "{target}" %*\r\n', encoding="utf-8")
        return
    dst = d / name
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(target)


def python_runner(script, env=None, args=None):
    """Script Python que executa outra ferramenta (substitui symlink, funciona em qualquer sistema)."""
    lines = ["import os, runpy, sys"]
    for k, v in (env or {}).items():
        lines.append(f"os.environ[{k!r}] = {str(v)!r}")
    argv = [str(script)] + [str(a) for a in (args or [])]
    lines.append(f"sys.argv = {argv!r} + sys.argv[2:]")
    lines.append(f"runpy.run_path({str(script)!r}, run_name='__main__')")
    return "\n".join(lines) + "\n"


def make_executable():
    if WINDOWS:
        return
    for p in list((REPO / "bin").iterdir()) + list((REPO / "git-hooks").iterdir()) + \
            list((REPO / ".githooks").iterdir()) + list((REPO / "agent-hooks").glob("*.py")) + \
            [REPO / "lib" / "runpy.sh", REPO / "install.py", REPO / "tools" / "privacy_gate.py"]:
        if p.is_file():
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def git(vault, *args):
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--personal-vault")
    ap.add_argument("--skip-extensions", action="store_true")
    ap.add_argument("--force-obsidian-config", action="store_true")
    ap.add_argument("--no-agents", action="store_true")
    a = ap.parse_args()

    vault = Path(a.vault).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)
    print(f"obsidian-config: {REPO}\nVault:           {vault}\nSistema:         {sys.platform}")

    say("1/9", "Dependências")
    missing = [c for c in ("git", "node") if not shutil.which(c)]
    ok(f"python {sys.version.split()[0]}")
    for c in ("git", "node"):
        (warn if c in missing else ok)(f"{c}{' não encontrado' if c in missing else ''}")
    if "git" in missing:
        sys.exit("git é obrigatório.")
    if "node" in missing:
        warn("Sem node o MCP server não roda. As demais ferramentas funcionam.")
    make_executable()

    say("2/9", "Configuração")
    vaultcfg.USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    vaultcfg.USER_CONFIG.write_text(json.dumps({"vault": str(vault)}, indent=2), encoding="utf-8")
    ok(vaultcfg.USER_CONFIG)
    cfg_file = vault / ".vault" / "config.json"
    if not cfg_file.is_file():
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "config.example.json", cfg_file)
        ok(f"{cfg_file} criado a partir do exemplo. Edite organizações e mounts.")
    else:
        ok(f"{cfg_file} já existe")
    os.environ["OBSIDIAN_VAULT_PATH"] = str(vault)
    cfg = vaultcfg.load(vault)

    shared = cfg.get("shared_repo", False)
    say("3/9", "Estrutura e templates")
    for d in cfg["expected_dirs"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    if shared:
        ok("vault compartilhado (shared_repo): templates e notas do repositório preservados")
    else:
        tdir = vault / "99 - Templates"
        tdir.mkdir(exist_ok=True)
        for t in (REPO / "templates").glob("*.md"):
            if not (tdir / t.name).exists():
                shutil.copy2(t, tdir / t.name)
        ok("pastas da taxonomia e templates ausentes criados (existentes preservados)")
    for src, key in (("policy-local.template.md", "policy_note"), ("agent-rules.template.md", "agent_rules_note")):
        if shared or not cfg.get("generate_agent_files", True):
            break  # vault de time: o contrato é o AGENTS.md dele
        dst = vault / cfg[key]
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "agents" / src, dst)
            ok(f"{cfg[key]} criado (edite para regras específicas deste vault)")

    say("4/9", "Obsidian")
    obs = vault / ".obsidian"
    (obs / "plugins").mkdir(parents=True, exist_ok=True)
    if shared:
        ok(".obsidian do repositório compartilhado preservado (só plugins e temas são baixados)")
    else:
        for f in (REPO / "obsidian").glob("*.json"):
            if f.name != "extensions.json" and (a.force_obsidian_config or not (obs / f.name).exists()):
                shutil.copy2(f, obs / f.name)
        for f in (REPO / "obsidian" / "plugin-settings").glob("*.json"):
            dst = obs / "plugins" / f.stem / "data.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if a.force_obsidian_config or not dst.exists():
                shutil.copy2(f, dst)
        ok(".obsidian base aplicado (existentes preservados; --force-obsidian-config sobrescreve)")
    if not a.skip_extensions:
        subprocess.call([sys.executable, "-X", "utf8", str(REPO / "lib" / "extensions.py"), str(REPO / "obsidian" / "extensions.json"), str(obs)])
    app_cfg = obsidian_app_config()
    app_cfg.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(app_cfg.read_text(encoding="utf-8")) if app_cfg.is_file() else {}
    except ValueError:
        data = {}
    vaults = data.setdefault("vaults", {})
    if not any(isinstance(v, dict) and Path(v.get("path", "")) == vault for v in vaults.values()):
        vaults[secrets.token_hex(8)] = {"path": str(vault), "ts": 0}
    data["cli"] = True
    app_cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    ok(f"vault registrado em {app_cfg}")

    say("5/9", f"Ferramentas no PATH ({bin_dir()})")
    for t in TOOLS:
        link_tool(t, REPO / "bin" / t)
    link_tool("validate-obsidian-work-vault", REPO / "bin" / "vault-validate")  # nome antigo
    ok(", ".join(TOOLS))
    if str(bin_dir()) not in os.environ.get("PATH", "").split(os.pathsep):
        warn(f"{bin_dir()} não está no PATH. Adicione ao PATH do seu shell/usuário.")

    say("6/9", "Git do vault e dos vaults montados")
    targets = [vault] + [vault / p for p in vaultcfg.shared_mount_paths(cfg)]
    for v in targets:
        if (v / ".git").exists():
            git(v, "config", "core.hooksPath", str(REPO / "git-hooks"))
            ok(f"core.hooksPath em {v.name}")
    git(REPO, "config", "core.hooksPath", ".githooks")
    ok("barreira de privacidade ativa no próprio obsidian-config (pre-commit e pre-push)")

    say("7/9", "Guards de privacidade locais (fora dos repositórios)")
    personal = Path(a.personal_vault).expanduser().resolve() if a.personal_vault else vault
    pcfg = vaultcfg.load(personal)
    guard = REPO / "bin" / "shared-vault-guard"
    for p in vaultcfg.shared_mount_paths(pcfg):
        mount = personal / p
        if not (mount / ".vault" / "config.json").is_file():
            continue
        name = vaultcfg.slugify(vaultcfg.load(mount)["vault_name"])
        d = vaultcfg.USER_CONFIG.parent / "pre-commit.d" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "10-personal-vault-guard.py").write_text(
            python_runner(guard, {"OBSIDIAN_VAULT_PATH": personal}, [mount]), encoding="utf-8")
        ok(f"guard do vault pessoal no pre-commit de '{p}'")
    if (personal / "01 - Organizations").is_dir():
        d = vaultcfg.USER_CONFIG.parent / "privacy.d"
        d.mkdir(parents=True, exist_ok=True)
        (d / "10-personal-vault-guard.py").write_text(
            python_runner(guard, {"OBSIDIAN_VAULT_PATH": personal}, ["--scan", REPO]), encoding="utf-8")
        ok("guard do vault pessoal na barreira do obsidian-config")

    say("8/9", "Agentes de IA")
    if a.no_agents:
        subprocess.call([sys.executable, "-X", "utf8", str(REPO / "bin" / "sync-agents"), "--vault-only", "--quiet"])
        ok("só arquivos de agente na raiz do vault (--no-agents)")
    else:
        subprocess.call([sys.executable, "-X", "utf8", str(REPO / "bin" / "sync-agents"), "--quiet"])
        ok("instruções, skills e MCP sincronizados (Claude Code, Gemini CLI, Codex)")
        claude = shutil.which("claude")
        if claude:
            sync = vaultcfg.load(vault)
            servers = [(sync.get("mcp_name", "obsidian-vault"), vault)]
            for p in vaultcfg.shared_mount_paths(sync):
                m = vault / p
                if (m / ".vault" / "config.json").is_file():
                    servers.append((vaultcfg.load(m).get("mcp_name") or vaultcfg.slugify(m.name), m))
            for name, v in servers:
                subprocess.run([claude, "mcp", "remove", name, "--scope", "user"], capture_output=True)
                subprocess.run([claude, "mcp", "add", name, "--scope", "user", "-e", f"OBSIDIAN_VAULT_PATH={v}",
                                "--", "node", str(REPO / "mcp-server" / "index.js")], capture_output=True)
            ok("Claude Code: " + ", ".join(n for n, _ in servers))
        gem = Path.home() / ".gemini"
        if gem.is_dir():
            (gem / "config").mkdir(exist_ok=True)
            schemas = gem / "antigravity" / "mcp" / "obsidian-vault"
            schemas.mkdir(parents=True, exist_ok=True)
            for f in list((REPO / "mcp-server" / "schemas").glob("*.json")) + [REPO / "mcp-server" / "instructions.md"]:
                shutil.copy2(f, schemas / f.name)
            cmd = lambda s: f'"{sys.executable}" -X utf8 "{REPO / "agent-hooks" / s}"'  # noqa: E731
            (gem / "config" / "hooks.json").write_text(json.dumps({"obsidian-vault-lifecycle": {
                "PreInvocation": [{"type": "command", "command": cmd("obsidian_session_init.py"), "timeout": 10}],
                "Stop": [{"type": "command", "command": cmd("obsidian_pre_stop.py"), "timeout": 20}],
            }}, indent=2), encoding="utf-8")
            ok("Gemini / Antigravity: schemas MCP e lifecycle hooks")

    say("9/9", "Validação")
    rc = subprocess.call([sys.executable, "-X", "utf8", str(REPO / "bin" / "vault-validate"), str(vault)])
    print("\nPronto." if rc == 0 else "\nA validação reportou problemas. Veja a saída acima.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
