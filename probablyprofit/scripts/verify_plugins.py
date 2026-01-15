#!/usr/bin/env python3
"""
Plugin System Verification

Demonstrates the plugin architecture functionality.
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import asyncio

from loguru import logger

from probablyprofit.plugins import PluginType, registry
from probablyprofit.plugins.examples import (
    MomentumStrategyPlugin,
    SlackNotificationPlugin,
    WhaleTrackerPlugin,
    list_example_plugins,
)
from probablyprofit.plugins.hooks import Hook, hooks


async def main():
    print("🔌 Plugin System Verification\n" + "=" * 50)

    # 1. List registered plugins
    plugins = list_example_plugins()
    print(f"\n📋 Registered Plugins: {plugins}")

    # 2. Create plugin instances
    whale_tracker = registry.create_instance(
        "whale_tracker", PluginType.DATA_SOURCE, min_bet_size=500.0
    )
    print(f"\n🐋 Created: {whale_tracker.__class__.__name__}")

    # 3. Test data source
    data = await whale_tracker.fetch("market_123")
    print(f"   Fetched data: {data}")

    # 4. Test strategy plugin
    momentum = registry.create_instance("momentum", PluginType.STRATEGY)
    print(f"\n📈 Momentum Strategy Prompt:\n{momentum.get_prompt()[:200]}...")

    # 5. Test hooks
    print("\n🔔 Testing Hooks...")

    @hooks.on(Hook.AFTER_TRADE, name="test_handler")
    async def test_trade_hook(data):
        print(f"   Hook received: {data}")
        return True

    results = await hooks.emit(Hook.AFTER_TRADE, {"action": "buy", "price": 0.45})
    print(f"   Hook results: {results}")

    # 6. List hook handlers
    print(f"\n📌 Active Hooks: {hooks.list_handlers()}")

    print("\n" + "=" * 50)
    print("✅ Plugin System Verified!")


if __name__ == "__main__":
    asyncio.run(main())
