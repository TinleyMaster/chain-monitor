"""Chain configuration constants for chain-monitor."""

CHAIN_NAMES = {
    "ethereum": "Ethereum",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "polygon": "Polygon",
    "solana": "Solana",
}

CHAIN_EXPLORER_TX = {
    "ethereum": "https://etherscan.io/tx/{tx}",
    "arbitrum": "https://arbiscan.io/tx/{tx}",
    "optimism": "https://optimistic.etherscan.io/tx/{tx}",
    "base": "https://basescan.org/tx/{tx}",
    "polygon": "https://polygonscan.com/tx/{tx}",
    "solana": "https://solscan.io/tx/{tx}",
}

DEFILLAMA_CHAIN_IDS = {
    "ethereum": "Ethereum",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "polygon": "Polygon",
    "solana": "Solana",
}

COVALENT_CHAIN_IDS = {
    "ethereum": "eth-mainnet",
    "arbitrum": "arbitrum-mainnet",
    "optimism": "optimism-mainnet",
    "base": "base-mainnet",
    "polygon": "matic-mainnet",
    "solana": "solana-mainnet",
}

EVM_CHAINS = {"ethereum", "arbitrum", "optimism", "base", "polygon"}


def get_explorer_url(chain: str, tx_hash: str) -> str:
    template = CHAIN_EXPLORER_TX.get(chain, "")
    return template.format(tx=tx_hash) if template else ""


def is_evm(chain: str) -> bool:
    return chain in EVM_CHAINS
