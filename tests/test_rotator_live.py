import asyncio
import logging
import sys
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

from backend.proxy_rotator import SocksProxyRotator, BLACK_LIST_SOURCES, WHITE_LIST_SOURCES

async def main():
    rotator = SocksProxyRotator()
    print("\n--- Testing Tier 1 (Black list) Live ---")
    res1 = await rotator._check_vpn_sources(BLACK_LIST_SOURCES, tier_name="Tier 1 Test")
    print(f"Tier 1 Result: {res1}")
    rotator.stop_tunnel()

    if not res1:
        print("\n--- Testing Tier 2 (White list) Live ---")
        res2 = await rotator._check_vpn_sources(WHITE_LIST_SOURCES, tier_name="Tier 2 Test")
        print(f"Tier 2 Result: {res2}")
        rotator.stop_tunnel()

if __name__ == "__main__":
    asyncio.run(main())
