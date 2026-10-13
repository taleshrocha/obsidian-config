#!/usr/bin/env python3
"""Regenera mcp-server/schemas/*.json a partir do tools/list do próprio MCP server.

Uso: python3 tools/gen_mcp_schemas.py [--check]   (--check: só compara, sai 1 se divergir)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "mcp-server" / "schemas"


def tools():
    env = dict(os.environ, OBSIDIAN_VAULT_PATH=tempfile.mkdtemp())
    msgs = "\n".join(json.dumps(m) for m in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})) + "\n"
    out = subprocess.run(["node", str(REPO / "mcp-server" / "index.js")], input=msgs, env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=30).stdout
    resp = [json.loads(l) for l in out.splitlines() if l.strip()]
    return next(r["result"]["tools"] for r in resp if r.get("id") == 2)


def render(t):
    return json.dumps({"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]},
                      indent=2, ensure_ascii=False) + "\n"


def main():
    check = "--check" in sys.argv
    wanted = {f"{t['name']}.json": render(t) for t in tools()}
    current = {p.name: p.read_text(encoding="utf-8") for p in SCHEMAS.glob("*.json")}
    if check:
        bad = sorted(set(wanted) ^ set(current)) + sorted(n for n in wanted if n in current and wanted[n] != current[n])
        print("schemas em dia" if not bad else f"schemas divergentes: {bad}")
        return 1 if bad else 0
    for p in SCHEMAS.glob("*.json"):
        if p.name not in wanted:
            p.unlink()
    for n, body in wanted.items():
        (SCHEMAS / n).write_text(body, encoding="utf-8")
    print(f"{len(wanted)} schemas gerados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
