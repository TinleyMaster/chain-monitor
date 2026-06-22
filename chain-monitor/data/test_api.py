import asyncio, aiohttp, json

async def test():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.llama.fi/v2/chains", timeout=10) as r:
            data = await r.json()
            for item in data:
                name = (item.get("name") or "").lower()
                if name in ("ethereum", "solana"):
                    tvl = item["tvl"] / 1e9
                    c1h = item.get("change_1h", 0) or 0
                    c24h = item.get("change_1d", 0) or 0
                    print(f"  {item['name']}: TVL=${tvl:.2f}B, 1h={c1h:.2f}%, 24h={c24h:.2f}%")
        async with s.get("https://api.llama.fi/v2/tokens/trending", timeout=10) as r:
            trends = await r.json()
            print(f"Trending: {len(trends)} results")
            for t in trends[:3]:
                vol = (t.get("volume_24h") or 0) / 1e6
                symbol = t.get("symbol") or "?"
                price = t.get("price") or 0
                print(f"  {symbol}: ${price:.4f}, vol=${vol:.1f}M")

asyncio.run(test())
