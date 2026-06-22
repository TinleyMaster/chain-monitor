"""Message formatters for chain-monitor alerts."""

from datetime import datetime


def format_whale_transfer(data: dict) -> str:
    chain = data.get("chain", "?").upper()
    token = data.get("token_symbol", "ETH")
    amount_usd = data.get("amount_usd", 0)
    amount = data.get("amount", 0)
    fr = data.get("from_address", "")
    to = data.get("to_address", "")
    tx = data.get("tx_hash", "")

    fr_short = f"{fr[:6]}...{fr[-4:]}" if len(fr) > 10 else fr
    to_short = f"{to[:6]}...{to[-4:]}" if len(to) > 10 else to

    from src.utils.chains import get_explorer_url
    explorer = get_explorer_url(data.get("chain", ""), tx)

    lines = [
        f"<b>\U0001f535 Whale Transfer | {chain}</b>",
        "",
        f"Token: {token}",
        f"Amount: ${amount_usd:,.0f} ({amount:,.2f} {token})",
        f"From:  <code>{fr_short}</code>",
        f"To:    <code>{to_short}</code>",
    ]
    if explorer:
        lines.append(f"<a href=\"{explorer}\">View on Explorer</a>")

    return "\n".join(lines)


def format_price_alert(data: dict) -> str:
    token = data.get("token", "?")
    price = data.get("price_usd", 0)
    change = data.get("change_pct", 0)
    prev = data.get("prev_price_usd")
    direction = "\U0001f7e2" if change >= 0 else "\U0001f534"

    lines = [
        f"<b>\U0001f4c8 Price Alert | {token}</b>",
        "",
        f"Current: ${price:,.4f}",
    ]
    if prev:
        lines.append(f"Previous: ${prev:,.4f}")
    lines.append(f"Change: {direction} {change:+.2f}%")

    if data.get("high_24h"):
        lines.append(f"24h High: ${data['high_24h']:,.4f}")
    if data.get("low_24h"):
        lines.append(f"24h Low:  ${data['low_24h']:,.4f}")

    return "\n".join(lines)


def format_tvl_alert(data: dict) -> str:
    chain = data.get("chain", "?").upper()
    tvl = data.get("tvl", 0)
    change = data.get("change_24h", 0) or 0
    direction = "\U0001f7e2" if change >= 0 else "\U0001f534"

    lines = [
        f"<b>\U0001f4ca TVL Alert | {chain}</b>",
        "",
        f"TVL: ${tvl/1e9:,.2f}B",
        f"24h Change: {direction} {change:+.1f}%",
    ]
    if data.get("change_1h") is not None:
        lines.append(f"1h Change: {data['change_1h']:+.1f}%")

    return "\n".join(lines)


def format_bignumber(n: int | float) -> str:
    if n >= 1_000_000_000:
        return f"{n/1e9:.2f}B"
    elif n >= 1_000_000:
        return f"{n/1e6:.2f}M"
    elif n >= 1_000:
        return f"{n/1e3:.2f}K"
    return f"{n:.2f}"
