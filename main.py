"""
ICT Trading Bot - Main Entry Point

An automated trading bot implementing Inner Circle Trader (ICT) concepts
for NAS100 (US100) using MetaTrader 5.
"""

from ict_bot import (
    market_structure,
    order_blocks,
    fvg,
    liquidity,
    kill_zones,
    ote,
    premium_discount,
)


def main():
    """Main entry point for the ICT trading bot."""
    print("ICT Trading Bot - NAS100")
    print("Modules loaded:")
    print(f"  - market_structure: {market_structure.__name__}")
    print(f"  - order_blocks: {order_blocks.__name__}")
    print(f"  - fvg: {fvg.__name__}")
    print(f"  - liquidity: {liquidity.__name__}")
    print(f"  - kill_zones: {kill_zones.__name__}")
    print(f"  - ote: {ote.__name__}")
    print(f"  - premium_discount: {premium_discount.__name__}")


if __name__ == "__main__":
    main()
