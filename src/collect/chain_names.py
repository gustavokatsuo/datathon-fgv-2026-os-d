"""Harmonização dos nomes de chain entre as bases da DefiLlama.

A base de hacks usa grafias livres ("Binance Smart Chain", "Optimism",
"Ripple"). O nome canônico adotado é o de https://api.llama.fi/v2/chains,
que também é usado por https://stablecoins.llama.fi/stablecoinchains.
Cada alias foi conferido manualmente contra as duas listas.
"""

from __future__ import annotations

# alias na base de hacks -> nome canônico (/v2/chains)
CHAIN_ALIASES: dict[str, str] = {
    "Binance Smart Chain": "BSC",
    "Binance": "BSC",
    "BNB": "BSC",
    "Optimism": "OP Mainnet",
    "zkSync Era": "ZKsync Era",
    "XRP": "XRPL",
    "Ripple": "XRPL",
    "TRON": "Tron",
    "Gnosis Chain": "Gnosis",
    "xDai": "Gnosis",
    "Terra": "Terra Classic",
    "BitcoinCash": "Bitcoincash",
    "Ethereum Classic": "EthereumClassic",
    "ETC": "EthereumClassic",
    "Elrond": "MultiversX",
    "NEAR": "Near",
    "Iota": "IOTA",
    "Wemix": "WEMIX3.0",
}

# chains da base de hacks ausentes de /v2/chains (sem TVL DeFi na DefiLlama),
# com o id CoinGecko da moeda nativa conferido manualmente
CHAIN_GECKO_FALLBACK: dict[str, str] = {
    "EOS": "eos",
    "Polkadot": "polkadot",
    "Secret": "secret",
    "Monero": "monero",
    "NEM": "nem",
    "Casper": "casper-network",
    "Nano": "nano",
    "Bitcoin Gold": "bitcoin-gold",
}

# rótulos que não identificam uma chain específica
NON_CHAIN_LABELS = {"Multiple", "Multi-Chain"}


def canonical_chain(name: str | None) -> str | None:
    if name is None or name in NON_CHAIN_LABELS:
        return None
    return CHAIN_ALIASES.get(name, name)
