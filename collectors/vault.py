from __future__ import annotations

import subprocess


def get_vault_credential(key_name: str, vault: str = "orbe-main") -> str:
    """Read a decrypted credential from Agent Vault CLI."""
    try:
        result = subprocess.run(
            ["agent-vault", "vault", "credential", "get", key_name, "--vault", vault],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
