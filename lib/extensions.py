#!/usr/bin/env python3
"""
Baixa plugins e temas do Obsidian nas versões fixadas em obsidian/extensions.json.
O repositório GitHub de cada um vem dos catálogos oficiais (obsidianmd/obsidian-releases),
então este repositório não redistribui código de terceiros.

Uso: extensions.py <extensions.json> <vault>/.obsidian
"""
import json
import sys
import urllib.request
from pathlib import Path

CATALOG = "https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master"


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    obs = Path(sys.argv[2])
    plugins = {p["id"]: p["repo"] for p in json.loads(fetch(f"{CATALOG}/community-plugins.json"))}
    themes = {t["name"]: t["repo"] for t in json.loads(fetch(f"{CATALOG}/community-css-themes.json"))}

    for p in spec.get("plugins", []):
        pid, ver = p["id"], p["version"]
        dst = obs / "plugins" / pid
        manifest = dst / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("version") == ver:
            print(f"  ✓ plugin {pid} {ver} (já instalado)")
            continue
        repo = plugins.get(pid)
        if not repo:
            print(f"  ✗ plugin {pid}: não está no catálogo oficial")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        base = f"https://github.com/{repo}/releases/download/{ver}"
        for asset, required in (("main.js", True), ("manifest.json", True), ("styles.css", False)):
            try:
                (dst / asset).write_bytes(fetch(f"{base}/{asset}"))
            except Exception as e:  # noqa: BLE001
                if required:
                    print(f"  ✗ plugin {pid}: falha ao baixar {asset} ({e})")
                    break
        else:
            print(f"  ✓ plugin {pid} {ver}")

    for t in spec.get("themes", []):
        name = t["name"]
        dst = obs / "themes" / name
        if (dst / "theme.css").is_file():
            print(f"  ✓ tema {name} (já instalado)")
            continue
        repo = themes.get(name)
        if not repo:
            print(f"  ✗ tema {name}: não está no catálogo oficial")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        try:
            for asset in ("theme.css", "manifest.json"):
                (dst / asset).write_bytes(fetch(f"https://raw.githubusercontent.com/{repo}/HEAD/{asset}"))
            print(f"  ✓ tema {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ tema {name}: {e}")


if __name__ == "__main__":
    main()
