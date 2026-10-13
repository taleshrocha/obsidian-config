#!/usr/bin/env python3
"""
privacy_gate: barreira que impede dado pessoal de entrar neste repositório público.

Checagens genéricas (versionadas, valem para qualquer pessoa):
  - caminho de home (/home/<user>, /Users/<user>, C:\\Users\\<user>)
  - e-mail (exceto example.*, noreply, git@)
  - IPv4 privado (10.x, 172.16-31.x, 192.168.x)
  - tokens e chaves (GitHub, GitLab, OpenAI/Anthropic, AWS, chave privada PEM)

Checagens locais (não versionadas): todo script em ~/.config/obsidian-config/privacy.d/
recebe o caminho do repositório e falha com código != 0 se achar algo. O install.py instala
ali o guard que cruza o repositório com a denylist gerada do seu vault pessoal.

Uso: privacy_gate.py [--repo DIR]
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCAL_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obsidian-config" / "privacy.d"

CHECKS = [
    ("caminho de home", re.compile(r"(?:/home/(?!user\b|runner\b)[a-z_][\w.-]*/|/Users/(?!user\b|runner\b)[A-Za-z][\w.-]*/|[A-Za-z]:\\\\?Users\\\\?(?!user\b|runneradmin\b)[A-Za-z][\w.-]*)")),
    ("e-mail", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.|exemplo\.|users\.noreply\.github\.com)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("IPv4 privado", re.compile(r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("token GitLab", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("chave de API", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("chave AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("chave privada", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
]
# Linhas com estes marcadores são exemplos documentados (padrões de regex, placeholders).
ALLOW_LINE = re.compile(r"privacy-gate: allow")
SELF = Path(__file__).resolve()


def files(repo):
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard"],
                         capture_output=True, text=True).stdout.splitlines()
    return [repo / f for f in out if (repo / f).is_file()]


def generic_scan(repo):
    hits = []
    for f in files(repo):
        if f.resolve() == SELF:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            if ALLOW_LINE.search(line):
                continue
            for label, pat in CHECKS:
                m = pat.search(line)
                if m and not m.group(0).startswith("git@"):
                    hits.append(f"{f.relative_to(repo).as_posix()}:{n}: {label}")
    return hits


def local_scan(repo):
    failed = []
    if not LOCAL_DIR.is_dir():
        return failed
    for hook in sorted(LOCAL_DIR.iterdir()):
        if hook.suffix == ".py":
            rc = subprocess.call([sys.executable, "-X", "utf8", str(hook), str(repo)])
        elif os.access(hook, os.X_OK):
            rc = subprocess.call([str(hook), str(repo)])
        else:
            continue
        if rc != 0:
            failed.append(hook.name)
    return failed


def main():
    repo = Path(sys.argv[sys.argv.index("--repo") + 1]).resolve() if "--repo" in sys.argv else REPO
    hits = generic_scan(repo)
    for h in hits:
        print(f"  ✗ {h}")
    failed = local_scan(repo)
    for name in failed:
        print(f"  ✗ verificação local falhou: {name}")
    if hits or failed:
        print("Barreira de privacidade: BLOQUEADO. Remova os dados acima antes de comitar ou publicar.")
        return 1
    print(f"Barreira de privacidade: OK ({len(files(repo))} arquivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
