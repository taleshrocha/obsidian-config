#!/usr/bin/env python3
"""
obsidian_session_init.py: Lifecycle Pre-Invocation Hook for Antigravity

Executa antes de o modelo ser invocado.
Na primeira invocação (invocationNum == 1), se o workspace estiver no vault ou se
houver interação com o vault, injeta lembrete sobre as diretrizes operacionais do Obsidian.
"""

import sys
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))
import vaultcfg  # noqa: E402


def main():
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        payload = {}

    inv_num = payload.get("invocationNum", 1)
    workspace_paths = payload.get("workspacePaths", [])

    vault_str = str(vaultcfg.vault_dir())
    is_vault_context = any(vault_str in str(wp) for wp in workspace_paths) or True

    # Only inject on invocation 1 to keep context lean
    if inv_num == 1 and is_vault_context:
        msg = (
            "[Obsidian Vault Integration Active]\n"
            f"Vault: {vault_str}\n"
            "MCP Tools: search_vault, read_metadata, get_outline, read_section, read_note, list_notes, get_architecture_topology, create_change_record, append_daily_log, get_backlinks, open_in_gui, validate_vault\n"
            "Guidelines: Zero secrets, preserve YAML frontmatter, validate links before finishing."
        )
        response = {
            "injectSteps": [
                {
                    "ephemeralMessage": msg
                }
            ]
        }
        print(json.dumps(response))
        return

    print(json.dumps({}))

if __name__ == "__main__":
    main()
