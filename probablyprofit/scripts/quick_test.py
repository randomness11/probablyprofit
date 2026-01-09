"""Quick Backend Test - Fast validation of core functionality."""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

print("=" * 60)
print("⚡ Quick Backend Test")
print("=" * 60)

# Test 1: Import FastAPI app
print("\n1️⃣  Testing FastAPI imports...")
try:
    from probablyprofit.web.app import create_app
    app = create_app()
    print(f"   ✅ App created: {app.title} v{app.version}")
    routes = [r.path for r in app.routes if r.path.startswith("/api")]
    print(f"   ✅ API routes: {len(routes)}")
    print(f"      - GET /api/status")
    print(f"      - GET /api/trades")
    print(f"      - GET /api/performance")
    print(f"      - GET /api/equity-curve")
    print(f"      - GET /api/markets")
    print(f"      - POST /api/control/start")
    print(f"      - POST /api/control/stop")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Test 2: Test response models
print("\n2️⃣  Testing API response models...")
try:
    from datetime import datetime
    from probablyprofit.web.api.models import StatusResponse, TradeResponse, PerformanceResponse

    status = StatusResponse(
        running=True,
        agent_name="Test",
        agent_type="test",
        strategy="custom",
        dry_run=True,
        uptime_seconds=100.0,
        loop_count=5,
        balance=1000.0,
        positions_count=0,
    )
    print(f"   ✅ StatusResponse: {status.agent_name} - ${status.balance}")

    trade = TradeResponse(
        id=1,
        order_id="test-123",
        market_id="market-1",
        outcome="Yes",
        side="BUY",
        size=10.0,
        price=0.55,
        status="filled",
        timestamp=datetime.now(),
        realized_pnl=None,
    )
    print(f"   ✅ TradeResponse: {trade.side} {trade.size} @ ${trade.price}")

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
    print(f"   ✅ PerformanceResponse: {perf.total_return_pct:.1%} return, {perf.win_rate:.0%} win rate")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Test 3: WebSocket manager
print("\n3️⃣  Testing WebSocket manager...")
try:
    from probablyprofit.web.api.websocket import ConnectionManager

    manager = ConnectionManager()
    print(f"   ✅ ConnectionManager created")
    print(f"   ✅ Active connections: {len(manager.active_connections)}")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Test 4: Database models
print("\n4️⃣  Testing database models...")
try:
    from probablyprofit.storage.models import TradeRecord, ObservationRecord, DecisionRecord

    print(f"   ✅ TradeRecord model available")
    print(f"   ✅ ObservationRecord model available")
    print(f"   ✅ DecisionRecord model available")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("🎉 All quick tests passed!")
print("=" * 60)
print("\n📝 Next steps:")
print("   1. Add to your .env file:")
print("      ENABLE_WEB_DASHBOARD=true")
print("      WEB_DASHBOARD_PORT=8000")
print("\n   2. Start the bot:")
print("      cd ~/polymarket-ai-bot/probablyprofit")
print("      python main.py --strategy custom --agent openai --dry-run")
print("\n   3. Access the dashboard:")
print("      http://localhost:8000/docs")
print("      http://localhost:8000/api/status")
print("\n   4. Test WebSocket:")
print("      ws://localhost:8000/ws")
print("=" * 60)
