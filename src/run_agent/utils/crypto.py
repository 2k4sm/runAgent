"""Symmetric encryption for secrets stored at rest.

Used to encrypt the `auth_config` column of `mcp_servers` (auth headers and
OAuth tokens). Keyed by `settings.mcp_encryption_key` — a Fernet key.
"""

from cryptography.fernet import Fernet

from run_agent.config.settings import settings


def _fernet() -> Fernet:
    key = settings.mcp_encryption_key
    if not key:
        raise RuntimeError(
            "MCP_ENCRYPTION_KEY is not set — required to store MCP server secrets. "
            "Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning an opaque token safe to store in the DB."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token produced by `encrypt`."""
    return _fernet().decrypt(token.encode()).decode()
