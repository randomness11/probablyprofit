"""
Test Backend

Quick test script to verify the FastAPI backend works.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


async def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing imports...")

    try:
        from probablyprofit.web.app import create_app
        print("  ✅ web.app imported")

        from probablyprofit.web.server import run_server_with_agent
        print("  ✅ web.server imported")

        from probablyprofit.web.api.routes import router
        print("  ✅ web.api.routes imported")

        from probablyprofit.web.api.websocket import manager, websocket_endpoint
        print("  ✅ web.api.websocket imported")

        from probablyprofit.web.api.models import StatusResponse, TradeResponse
        print("  ✅ web.api.models imported")

        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


async def test_app_creation():
    """Test that FastAPI app can be created."""
    print("\n🧪 Testing FastAPI app creation...")

    try:
        from probablyprofit.web.app import create_app

        app = create_app()
        print(f"  ✅ App created: {app.title}")
        print(f"  ✅ Version: {app.version}")

        # Check routes
        routes = [route.path for route in app.routes]
        print(f"  ✅ Total routes: {len(routes)}")

        # Check API routes
        api_routes = [r for r in routes if r.startswith("/api")]
        print(f"  ✅ API routes: {len(api_routes)}")
        for route in api_routes[:5]:
            print(f"     - {route}")

        # Check WebSocket
        ws_routes = [r for r in routes if "ws" in r.lower()]
        print(f"  ✅ WebSocket routes: {len(ws_routes)}")

        return True
    except Exception as e:
        print(f"  ❌ App creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_integration():
    """Test database integration."""
    print("\n🧪 Testing database integration...")

    try:
        from probablyprofit.storage.database import get_db_manager, initialize_database
        from probablyprofit.storage.models import TradeRecord, ObservationRecord, DecisionRecord

        print("  ✅ Database models imported")

        # Try to initialize database
        db_manager = get_db_manager()
        print(f"  ✅ Database manager created: {db_manager.database_url}")

        await initialize_database()
        print("  ✅ Database initialized")

        return True
    except Exception as e:
        print(f"  ⚠️  Database test: {e}")
        return False


async def test_mock_agent_state():
    """Test setting mock agent state."""
    print("\n🧪 Testing agent state management...")

    try:
        from probablyprofit.web.app import set_agent_state, get_agent_state
        from probablyprofit.agent.base import BaseAgent, AgentMemory, Observation, Decision
        from probablyprofit.risk.manager import RiskManager
        from datetime import datetime

        # Create mock components (skip PolymarketClient)
        risk = RiskManager(initial_capital=1000.0)

        # Create minimal mock agent (without full initialization)
        class MockAgent:
            def __init__(self):
                self.name = "TestAgent"
                self.running = False
                self.dry_run = True
                self.memory = AgentMemory()
                self.risk_manager = risk

        agent = MockAgent()

        # Set agent state
        set_agent_state(agent, "test", "mock-strategy")
        print("  ✅ Agent state set")

        # Get agent state
        state = get_agent_state()
        print(f"  ✅ Agent state retrieved: {state.agent_type}")
        print(f"  ✅ Strategy: {state.strategy_name}")
        print(f"  ✅ Uptime: {state.uptime_seconds:.2f}s")

        return True
    except Exception as e:
        print(f"  ❌ Agent state test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test API endpoint logic (without HTTP)."""
    print("\n🧪 Testing API endpoint logic...")

    try:
        from datetime import datetime
        from probablyprofit.web.api.models import (
            StatusResponse,
            TradeResponse,
            PerformanceResponse,
            EquityCurvePoint,
            MarketResponse,
        )

        # Test model creation
        status = StatusResponse(
            running=True,
            agent_name="TestAgent",
            agent_type="test",
            strategy="custom",
            dry_run=True,
            uptime_seconds=123.45,
            loop_count=10,
            balance=1000.0,
            positions_count=3,
        )
        print(f"  ✅ StatusResponse created: {status.agent_name}")

        trade = TradeResponse(
            id=1,
            order_id="test-123",
            market_id="market-abc",
            outcome="Yes",
            side="BUY",
            size=10.0,
            price=0.55,
            status="filled",
            timestamp=datetime.now(),
            realized_pnl=2.50,
        )
        print(f"  ✅ TradeResponse created: {trade.outcome} {trade.side}")

        perf = PerformanceResponse(
            current_capital=1050.0,
            initial_capital=1000.0,
            total_return=50.0,
            total_return_pct=0.05,
            total_pnl=50.0,
            daily_pnl=10.0,
            win_rate=0.75,
            total_trades=20,
        )
        print(f"  ✅ PerformanceResponse created: {perf.total_return_pct:.1%} return")

        return True
    except Exception as e:
        print(f"  ❌ API endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("🚀 probablyprofit Backend Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Imports", await test_imports()))
    results.append(("App Creation", await test_app_creation()))
    results.append(("Database Integration", await test_database_integration()))
    results.append(("Mock Agent State", await test_mock_agent_state()))
    results.append(("API Endpoints", await test_api_endpoints()))

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("=" * 60)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 All tests passed! Backend is ready.")
        print("\nNext steps:")
        print("  1. Set ENABLE_WEB_DASHBOARD=true in your .env")
        print("  2. Run: python probablyprofit/main.py --strategy custom --agent openai --dry-run")
        print("  3. Open: http://localhost:8000/docs")
    else:
        print("\n⚠️  Some tests failed. Check errors above.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
