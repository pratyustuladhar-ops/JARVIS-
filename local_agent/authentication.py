import os
import hmac
import hashlib
import logging
from typing import Optional
from local_agent.config import AUTH_TOKEN

logger = logging.getLogger("jarvis.local_agent.auth")

CREDENTIAL_STORE_PATH = os.path.expanduser("~/.jarvis_agent_token")


def get_agent_token() -> str:
    """
    Retrieves the agent authentication token from environment, local secret file, or config.
    """
    env_token = os.environ.get("JARVIS_LOCAL_AGENT_TOKEN")
    if env_token:
        return env_token.strip()

    if os.path.exists(CREDENTIAL_STORE_PATH):
        try:
            with open(CREDENTIAL_STORE_PATH, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
        except Exception as e:
            logger.warning(f"Could not read local credential store: {e}")

    return AUTH_TOKEN


def store_agent_token(token: str) -> bool:
    """Securely stores agent token on the local machine."""
    try:
        with open(CREDENTIAL_STORE_PATH, "w", encoding="utf-8") as f:
            f.write(token.strip())
        return True
    except Exception as e:
        logger.error(f"Failed to store agent credential locally: {e}")
        return False


def verify_agent_token(provided_token: Optional[str]) -> bool:
    """
    Verifies that the incoming request token matches the configured agent token
    using constant-time comparison to protect against timing attacks.
    """
    if not provided_token:
        return False

    expected_token = get_agent_token()
    return hmac.compare_digest(provided_token.strip(), expected_token.strip())


def get_auth_headers(token: Optional[str] = None) -> dict:
    """Returns the authorization headers for contacting the JARVIS backend."""
    active_token = token or get_agent_token()
    return {
        "Content-Type": "application/json",
        "X-Local-Agent-Token": active_token
    }
