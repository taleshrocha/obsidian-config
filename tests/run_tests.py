#!/usr/bin/env python3
"""
Testes do obsidian-config. Rodam em Linux, macOS e Windows, sem tocar na máquina real:
cada teste usa HOME, XDG_CONFIG_HOME e vaults temporários.

Uso: python3 tests/run_tests.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin"
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402

DIRS = vaultcfg.DEFAULTS["expected_dirs"]


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


class Base(unittest.TestCase):
    def setUp(self):
        # resolve(): no Windows o temp vem em formato curto (RUNNER~1)
        self.tmp = Path(tempfile.mkdtemp(prefix="obsidian-config-test-")).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / ".config"), VAULT_AUTHOR="Dev Teste", NO_COLOR="1",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, tool, *args, vault=None, input_text=None):
        env = dict(self.env)
        if vault:
            env["OBSIDIAN_VAULT_PATH"] = str(vault)
        return subprocess.run([sys.executable, "-X", "utf8", str(BIN / tool), *map(str, args)], env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", input=input_text)

    def make_vault(self, name="vault", **cfg):
        v = self.tmp / name
        for d in cfg.get("expected_dirs", DIRS):
            (v / d).mkdir(parents=True, exist_ok=True)
        base = {"vault_name": name, "generate_agent_files": False}
        base.update(cfg)
        write(v / ".vault" / "config.json", json.dumps(base))
        write(v / "AGENTS.md", "# Contrato\n")
        write(v / "CLAUDE.md", "@AGENTS.md\n")
        write(v / "GEMINI.md", "@AGENTS.md\n")
        return v


class TestValidator(Base):
    def test_minimal_vault_passes(self):
        v = self.make_vault()
        write(v / "04 - Servers" / "app-01.md", """
            ---
            type: server
            environment: production
            ---
            # app-01
            """)
        r = self.run_tool("vault-validate", v, vault=v)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_broken_link_fails(self):
        v = self.make_vault()
        write(v / "02 - Projects" / "p.md", "---\ntype: project\n---\n[[nao-existe]]\n")
        r = self.run_tool("vault-validate", v, vault=v)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nao-existe", r.stdout)

    def test_privacy_checks(self):
        cases = {
            "email": "- contato fulano@empresa.com.br\n",  # privacy-gate: allow
            "telefone": "- ligar (84) 99999-1234\n",
            "home": "- cd /home/fulano/repos\n",  # privacy-gate: allow
            "senha": "- Senha: `123`\n",
            "dataview sem escopo": "```dataview\nLIST FROM \"04 - Servers\"\n```\n",
        }
        for label, body in cases.items():
            with self.subTest(label):
                v = self.make_vault(name=f"team-{label.replace(' ', '-')}", privacy_checks=True)
                write(v / "10 - Procedures" / "p.md", "---\ntype: procedure\n---\n" + body)
                r = self.run_tool("vault-validate", v, vault=v)
                self.assertNotEqual(r.returncode, 0, f"{label} deveria falhar")
        v = self.make_vault(name="team-ok", privacy_checks=True)
        write(v / "00 - Dashboard" / "d.md", textwrap.dedent("""\
            ---
            type: dashboard
            ---
            ```dataview
            LIST FROM ""
            WHERE startswith(file.folder, replace(this.file.folder, "00 - Dashboard", "04 - Servers"))
            ```
            """))
        r = self.run_tool("vault-validate", v, vault=v)
        self.assertEqual(r.returncode, 0, r.stdout)


class TestPrivacyOptions(Base):
    def test_allowed_home_users_and_exempt_paths(self):
        v = self.make_vault(name="team-opts", privacy_checks=True, privacy_allow_home_users=["deploy"],
                            privacy_exempt_paths=["10 - Procedures/Credenciais.md"])
        write(v / "10 - Procedures" / "a.md", "---\ntype: procedure\n---\n- cd /home/deploy/app\n")  # privacy-gate: allow
        write(v / "10 - Procedures" / "Credenciais.md", "---\ntype: procedure\n---\n- Senha: `123`\n")
        r = self.run_tool("vault-validate", v, vault=v)
        self.assertEqual(r.returncode, 0, r.stdout)
        write(v / "10 - Procedures" / "b.md", "---\ntype: procedure\n---\n- Senha: `123`\n- cd /home/fulano\n")  # privacy-gate: allow
        r = self.run_tool("vault-validate", v, vault=v)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("b.md", r.stdout)


class TestCli(Base):
    def test_new_log_meta_change(self):
        v = self.make_vault(change_id_author=True, journal={"dir": "13 - Journal", "per_author": True, "type": "journal"},
                            expected_dirs=[d for d in DIRS if d != "13 - Meetings"] + ["13 - Journal"])
        shutil.copytree(REPO / "templates", v / "99 - Templates", dirs_exist_ok=True)
        r = self.run_tool("vault", "new", "server", "app-01", "--env", "testing", vault=v)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((v / "04 - Servers" / "app-01.md").is_file())
        r = self.run_tool("vault", "log", "teste", vault=v)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list((v / "13 - Journal" / "dev-teste").glob("*.md"))), 1)
        r = self.run_tool("vault", "meta", "app-01", vault=v)
        self.assertIn("type: server", r.stdout)
        r = self.run_tool("vault", "change", "Teste", vault=v, input_text="app-01\n\nCross-Organization\nlow\nx\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [f.name for f in (v / "08 - Changes").rglob("CHG-*.md")]
        self.assertTrue(ids and "-dev-teste-001" in ids[0], ids)


@unittest.skipUnless(shutil.which("node"), "node ausente")
class TestMcp(Base):
    def test_schemas_match_tools_list(self):
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools" / "gen_mcp_schemas.py"), "--check"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def call(self, v, *msgs):
        env = dict(self.env, OBSIDIAN_VAULT_PATH=str(v))
        lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})]
        lines += [json.dumps({"jsonrpc": "2.0", "id": i + 2, "method": "tools/call", "params": m}) for i, m in enumerate(msgs)]
        r = subprocess.run(["node", str(REPO / "mcp-server" / "index.js")], input="\n".join(lines) + "\n",
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]

    def test_team_change_and_journal(self):
        v = self.make_vault(change_id_author=True, mcp_name="team-vault",
                            journal={"dir": "13 - Journal", "per_author": True, "type": "journal"})
        out = self.call(v, {"name": "create_change_record", "arguments": {"title": "T", "server": "", "service": "",
                                                                            "project": "P", "description": "d"}},
                        {"name": "append_daily_log", "arguments": {"content": "x"}})
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "team-vault")
        self.assertIn("CHG-", out[1]["result"]["content"][0]["text"])
        self.assertIn("dev-teste-001", out[1]["result"]["content"][0]["text"])
        self.assertTrue(list((v / "13 - Journal" / "dev-teste").glob("*.md")))

    def test_shared_repo_pulls_before_tool(self):
        git = lambda *a, cwd: subprocess.run(["git", *a], cwd=cwd, env=self.env, check=True, capture_output=True)
        origin = self.tmp / "origin.git"
        git("init", "--bare", "-b", "main", str(origin), cwd=self.tmp)
        v = self.make_vault(name="team", shared_repo=True, mcp_name="team-vault")
        git("init", "-b", "main", cwd=v)
        git("-c", "user.name=a", "-c", "user.email=a@x", "commit", "--allow-empty", "-m", "init", cwd=v)
        git("remote", "add", "origin", str(origin), cwd=v)
        git("push", "-u", "origin", "main", cwd=v)
        colega = self.tmp / "colega"
        git("clone", str(origin), str(colega), cwd=self.tmp)
        write(colega / "10 - Procedures" / "Novo.md", "---\ntype: procedure\n---\nchave-recem-publicada\n")
        git("add", "-A", cwd=colega)
        git("-c", "user.name=b", "-c", "user.email=b@x", "commit", "-m", "novo", cwd=colega)
        git("push", cwd=colega)
        out = self.call(v, {"name": "search_vault", "arguments": {"query": "chave-recem-publicada"}})
        text = out[1]["result"]["content"][0]["text"]
        self.assertIn("Novo.md", text)
        self.assertNotIn("[aviso]", text)


class TestGuard(Base):
    def test_detects_personal_terms_in_mount(self):
        p = self.make_vault(name="personal", shared_mounts=[{"path": "17 - Team", "organization": "Team",
                                                            "roster": "15 - Team/Equipe.md"}])
        write(p / "01 - Organizations" / "Acme.md", "---\ntype: organization\ncode: ACME\n---\n")
        write(p / "04 - Servers" / "acme-db.md", "---\ntype: server\nip_address: 10.9.9.9\n---\n")  # privacy-gate: allow
        m = self.make_vault(name="personal/17 - Team")
        write(m / "15 - Team" / "Equipe.md", "## Fulana\n")
        write(m / "10 - Procedures" / "x.md", "---\ntype: procedure\n---\nFulana ajusta o banco.\n")
        r = self.run_tool("shared-vault-guard", vault=p)
        self.assertEqual(r.returncode, 0, r.stdout)
        write(m / "10 - Procedures" / "y.md", "---\ntype: procedure\n---\nVer acme-db em 10.9.9.9\n")  # privacy-gate: allow
        r = self.run_tool("shared-vault-guard", vault=p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("acme-db", r.stdout)


class TestNestedMount(Base):
    def test_mount_inside_shared_vaults_folder(self):
        p = self.make_vault(name="personal", shared_mounts=[{"path": "80 - Shared Vaults/Time", "organization": "Time"}])
        write(p / "04 - Servers" / "meu-pc.md", "---\ntype: server\nenvironment: local\n---\n")
        m = self.make_vault(name="personal/80 - Shared Vaults/Time")
        write(m / "04 - Servers" / "app-01.md", "---\ntype: server\nenvironment: production\n---\n[[meu-pc]]\n")
        r = self.run_tool("vault-validate", p, vault=p)
        self.assertNotIn("Unexpected top-level directory", r.stdout)
        self.assertNotEqual(r.returncode, 0)  # o mount linka nota pessoal: o guard precisa acusar
        self.assertIn("meu-pc", r.stdout)
        (m / "04 - Servers" / "app-01.md").write_text("---\ntype: server\nenvironment: production\n---\n", encoding="utf-8")
        r = self.run_tool("vault-validate", p, vault=p)
        self.assertEqual(r.returncode, 0, r.stdout)


class TestSyncAgents(Base):
    def test_generates_instructions_and_merges_mcp(self):
        v = self.make_vault(name="personal", generate_agent_files=True)
        write(v / "07 - Infrastructure" / "AI" / "Shared Agent Policy.md", "---\ntype: procedure\n---\n# Política\n")
        write(v / "07 - Infrastructure" / "AI" / "Agent Rules.md", "---\ntype: procedure\n---\n# Agent Rules\n\n12. **Regra privada de teste** em {{VAULT_DIR}}\n")
        write(self.home / ".codex" / "config.toml", '[mcp_servers.outro]\ncommand = "x"\n\n[mcp_servers.obsidian-vault]\ncommand = "velho"\n')
        r = self.run_tool("sync-agents", "--quiet", vault=v)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        claude = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Regra privada de teste", claude)
        self.assertIn(str(v), claude)
        toml = (self.home / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.outro]", toml)
        self.assertEqual(toml.count("[mcp_servers.obsidian-vault]"), 1)
        self.assertNotIn("velho", toml)
        r = self.run_tool("sync-agents", "--check-vault-only", "--quiet", vault=v)
        self.assertEqual(r.returncode, 0)


class TestAgentPolicy(Base):
    def test_managed_block_preserves_user_content(self):
        v = self.make_vault(name="personal", generate_agent_files=True)
        write(self.home / ".claude" / "CLAUDE.md", "# Minhas regras\n\nNunca usar tabs.\n")
        self.assertEqual(self.run_tool("sync-agents", "--quiet", vault=v).returncode, 0)
        text = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Nunca usar tabs.", text)
        self.assertIn("<!-- obsidian-config:begin -->", text)
        self.assertIn("agents/policy.md", text)
        self.assertEqual(self.run_tool("sync-agents", "--quiet", vault=v).returncode, 0)
        again = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(again.count("<!-- obsidian-config:begin -->"), 1)
        self.assertIn("Nunca usar tabs.", again)

    def test_team_vault_as_primary_gets_global_policy(self):
        v = self.make_vault(name="team", generate_agent_files=False)
        self.assertEqual(self.run_tool("sync-agents", "--quiet", vault=v).returncode, 0)
        text = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("agents/policy.md", text)
        self.assertIn("contrato do vault de time", text)
        self.assertEqual((v / "AGENTS.md").read_text(encoding="utf-8"), "# Contrato\n")
        codex = (self.home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Loop engineering", codex)  # política base embutida para o Codex
        self.assertIn("# Contrato", codex)
        gemini = (self.home / ".gemini" / "GEMINI.md").read_text(encoding="utf-8")
        self.assertIn("Loop engineering", gemini)  # Antigravity CLI também não resolve @import
        self.assertIn("# Contrato", gemini)

    def test_install_creates_policy_and_rules_notes(self):
        v = self.tmp / "novo-pessoal"
        subprocess.run(["git", "init", "-q", str(v)], check=True)
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "install.py"), "--vault", str(v), "--skip-extensions"],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((v / "07 - Infrastructure" / "AI" / "Shared Agent Policy.md").is_file())
        self.assertTrue((v / "07 - Infrastructure" / "AI" / "Agent Rules.md").is_file())
        text = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Política local (prevalece", text)
        # Import fora de crase (crase desativa o @import) e com espaços escapados.
        self.assertIn("Shared\\ Agent\\ Policy.md", text)
        self.assertNotIn("`@", text)


class TestInstallAndGate(Base):
    def test_install_fresh_vault(self):
        v = self.tmp / "novo"
        subprocess.run(["git", "init", "-q", str(v)], check=True)
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "install.py"), "--vault", str(v), "--skip-extensions", "--no-agents"],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        shim = self.home / ".local" / "bin" / ("vault.cmd" if os.name == "nt" else "vault")
        self.assertTrue(shim.exists() or shim.is_symlink())
        self.assertTrue((v / ".vault" / "config.json").is_file())

    def test_install_leaves_shared_repo_clean(self):
        v = self.make_vault(name="time", shared_repo=True, generate_agent_files=False)
        write(v / ".gitignore", ".obsidian/plugins/\n.obsidian/themes/\n.obsidian/workspace.json\n")
        subprocess.run(["git", "init", "-q", str(v)], check=True)
        subprocess.run(["git", "-C", str(v), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(v), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"], check=True)
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "install.py"), "--vault", str(v), "--skip-extensions"],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        status = subprocess.run(["git", "-C", str(v), "status", "--porcelain"], capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), "", status)

    def test_uninstall_reverts_install(self):
        v = self.tmp / "vault-u"
        subprocess.run(["git", "init", "-q", str(v)], check=True)
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "install.py"), "--vault", str(v), "--skip-extensions"],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.home / ".claude" / "CLAUDE.md").is_file())
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "uninstall.py"), "--vault", str(v)],
                           env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertFalse((self.home / ".config" / "obsidian-config").exists())
        left = [p.name for p in (self.home / ".local" / "bin").iterdir()] if (self.home / ".local" / "bin").exists() else []
        self.assertEqual(left, [], left)
        hooks = subprocess.run(["git", "-C", str(v), "config", "core.hooksPath"], capture_output=True, text=True).stdout
        self.assertEqual(hooks.strip(), "")
        self.assertTrue((v / ".vault" / "config.json").is_file())  # conteúdo do vault preservado

    def test_privacy_gate_clean(self):
        r = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools" / "privacy_gate.py")], env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)


class TeamVaultAndAuthTests(Base):
    def test_vault_new_overrides_template_org(self):
        v = self.make_vault(organizations=["Org A"])
        write(v / "99 - Templates" / "Server.md", "---\ntype: server\nname: \norganization: Org B\n---\n# {{name}}\n")
        r = self.run_tool("vault", "new", "server", "app-01", vault=v)  # org única vira padrão
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        note = next((v / "04 - Servers").rglob("app-01.md")).read_text(encoding="utf-8")
        self.assertIn("organization: Org A", note)
        self.assertNotIn("Org B", note)

    def test_token_resolution_env_file_and_missing(self):
        env_name = "TESTE_TOKEN_GIT"
        rule = {"host_contains": "git.example.com", "token_env": env_name,
                "token_file": str(self.home / "nao-existe")}
        os.environ[env_name] = "abc"
        try:
            self.assertEqual(vaultcfg.resolve_token(rule, "https://git.example.com/x.git"), "abc")
            args = vaultcfg.https_auth_args({"git_https_auth": [rule]}, "https://git.example.com/x.git")
            self.assertEqual(args[0], "-c")
            self.assertTrue(args[1].startswith("http.extraheader=Authorization: Basic "))
        finally:
            del os.environ[env_name]
        tok_file = write(self.home / "tok", "xyz\n")
        self.assertEqual(vaultcfg.resolve_token({"token_file": str(tok_file)}, "https://git.example.com/"), "xyz")
        self.assertEqual(vaultcfg.https_auth_args({"git_https_auth": [rule]}, "https://outro.example.com/"), [])

    def test_auth_setup_check_reports_missing_and_ready(self):
        v = self.make_vault(git_https_auth=[{"host_contains": "git.example.com", "token_env": "TESTE_TOKEN_SETUP"}])
        env = dict(self.env)
        r = subprocess.run([sys.executable, "-X", "utf8", str(BIN / "vault"), "auth", "setup", "--check"],
                           env=dict(env, OBSIDIAN_VAULT_PATH=str(v), GIT_TERMINAL_PROMPT="0"),
                           capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("sem token", r.stdout)
        r = subprocess.run([sys.executable, "-X", "utf8", str(BIN / "vault"), "auth", "setup", "--check"],
                           env=dict(env, OBSIDIAN_VAULT_PATH=str(v), TESTE_TOKEN_SETUP="abc"),
                           capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("variável TESTE_TOKEN_SETUP", r.stdout)

    def test_agent_backup_snapshots_only_on_change_and_skips_secrets(self):
        write(self.home / ".claude" / "CLAUDE.md", "regras\n")
        write(self.home / ".claude" / ".credentials.json", "{}")
        write(self.home / ".claude" / "history.jsonl", "x\n")
        write(self.home / ".gemini" / "GEMINI.md", "g\n")
        dest = self.tmp / "bk"
        v = self.make_vault(agent_backup={"dest": str(dest)})
        r = self.run_tool("agent-backup", vault=v)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        snaps = list(dest.glob("agents-*.tar.gz"))
        self.assertEqual(len(snaps), 1)
        import tarfile
        names = tarfile.open(snaps[0]).getnames()
        self.assertIn(".claude/CLAUDE.md", names)
        self.assertIn(".gemini/GEMINI.md", names)
        self.assertNotIn(".claude/.credentials.json", names)
        self.assertNotIn(".claude/history.jsonl", names)
        self.run_tool("agent-backup", vault=v)
        self.assertEqual(len(list(dest.glob("agents-*.tar.gz"))), 1)  # sem mudança, sem novo snapshot

    def test_maintainer_gate_blocks_other_clones(self):
        repo = self.tmp / "clone"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=self.env)
        gate = REPO / "lib" / "maintainer_gate.sh"
        blocked = subprocess.run(["sh", str(gate)], cwd=repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 1)
        subprocess.run(["git", "-C", str(repo), "config", "obsidian-config.maintainer", "true"], check=True, env=self.env)
        allowed = subprocess.run(["sh", str(gate)], cwd=repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
