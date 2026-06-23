"""Configuration loader for chain-monitor. Reads config.yaml and exposes settings."""

import os
import yaml
from pathlib import Path

_config = None
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def get_config(reload: bool = False) -> dict:
    global _config
    if _config is not None and not reload:
        return _config
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {_CONFIG_PATH}")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    _apply_env_overrides()
    return _config


def _apply_env_overrides():
    """Allow environment variables to override config values."""
    env_map = {
        "ALCHEMY_ETH_KEY": ("api_keys", "alchemy", "eth-mainnet"),
        "ALCHEMY_ARB_KEY": ("api_keys", "alchemy", "arbitrum"),
        "ALCHEMY_OP_KEY": ("api_keys", "alchemy", "optimism"),
        "ALCHEMY_BASE_KEY": ("api_keys", "alchemy", "base"),
        "ALCHEMY_POLYGON_KEY": ("api_keys", "alchemy", "polygon"),
        "HELIUS_SOLANA_KEY": ("api_keys", "helius", "solana"),
        "TELEGRAM_BOT_TOKEN": ("api_keys", "telegram", "bot_token"),
        "TELEGRAM_CHAT_ID": ("api_keys", "telegram", "chat_id"),
    }
    for env_var, path in env_map.items():
        val = os.environ.get(env_var)
        if val:
            d = _config
            for key in path[:-1]:
                d = d.setdefault(key, {})
            d[path[-1]] = val


def get_alchemy_key(chain: str) -> str:
    cfg = get_config()
    key_map = {
        "ethereum": "eth-mainnet",
        "arbitrum": "arbitrum",
        "optimism": "optimism",
        "base": "base",
        "polygon": "polygon",
    }
    subkey = key_map.get(chain, chain)
    return cfg["api_keys"]["alchemy"].get(subkey, "")


def get_alchemy_ws_url(chain: str) -> str:
    key = get_alchemy_key(chain)
    ws_suffix = {
        "ethereum": "eth-mainnet",
        "arbitrum": "arb-mainnet",
        "optimism": "opt-mainnet",
        "base": "base-mainnet",
        "polygon": "polygon-mainnet",
    }
    sub = ws_suffix.get(chain, chain)
    return f"wss://{sub}.g.alchemy.com/v2/{key}"

def get_evm_ws_url(chain: str) -> str:
    """Get WebSocket URL for EVM chain.
    Priority: Alchemy key -> public RPC (free, no registration)."""
    from src.utils.chains import PUBLIC_RPC_WS
    key = get_alchemy_key(chain)
    if key and "YOUR_" not in key:
        return get_alchemy_ws_url(chain)
    url = PUBLIC_RPC_WS.get(chain)
    if url:
        import logging
        logging.getLogger(__name__).info(
            "No Alchemy key for %s, falling back to public RPC", chain
        )
    return url or ""
