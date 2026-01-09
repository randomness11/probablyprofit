"""
REST API Routes

All REST API endpoints for the dashboard.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from loguru import logger

from probablyprofit.web.api.models import (
    StatusResponse,
    TradeResponse,
    PerformanceResponse,
    EquityCurvePoint,
    MarketResponse,
)

router = APIRouter(prefix="/api")


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current agent status."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    last_obs = None
    balance = 0.0
    positions_count = 0

    if state.agent.memory.observations:
        last_obs = state.agent.memory.observations[-1].timestamp
        balance = state.agent.memory.observations[-1].balance
        positions_count = len(state.agent.memory.observations[-1].positions)

    return StatusResponse(
        running=state.agent.running,
        agent_name=state.agent.name,
        agent_type=state.agent_type,
        strategy=state.strategy_name,
        dry_run=state.agent.dry_run,
        uptime_seconds=state.uptime_seconds,
        loop_count=len(state.agent.memory.observations),
        last_observation=last_obs,
        balance=balance,
        positions_count=positions_count,
    )


@router.get("/trades", response_model=List[TradeResponse])
async def get_trades(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    market_id: Optional[str] = None,
):
    """Get trade history."""
    from probablyprofit.storage.database import get_db_manager
    from probablyprofit.storage.repositories import TradeRepository

    try:
        db = get_db_manager()
        async with db.get_session() as session:
            if market_id:
                trades = await TradeRepository.get_by_market(session, market_id)
            else:
                trades = await TradeRepository.get_recent(session, limit)

            return [
                TradeResponse(
                    id=trade.id,
                    order_id=trade.order_id,
                    market_id=trade.market_id,
                    outcome=trade.outcome,
                    side=trade.side,
                    size=trade.size,
                    price=trade.price,
                    status=trade.status,
                    timestamp=trade.timestamp,
                    realized_pnl=trade.realized_pnl,
                )
                for trade in trades[offset : offset + limit]
            ]
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance():
    """Get current performance metrics."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    stats = state.agent.risk_manager.get_stats()

    return PerformanceResponse(
        current_capital=stats["current_capital"],
        initial_capital=state.agent.risk_manager.initial_capital,
        total_return=stats["total_pnl"],
        total_return_pct=stats["return_pct"],
        total_pnl=stats["total_pnl"],
        daily_pnl=stats["daily_pnl"],
        win_rate=stats["win_rate"],
        total_trades=stats["total_trades"],
    )


@router.get("/equity-curve", response_model=List[EquityCurvePoint])
async def get_equity_curve(days: int = Query(30, ge=1, le=365)):
    """Get equity curve data."""
    from probablyprofit.storage.database import get_db_manager
    from probablyprofit.storage.repositories import PerformanceRepository

    try:
        db = get_db_manager()
        async with db.get_session() as session:
            snapshots = await PerformanceRepository.get_equity_curve(session, days)

            return [
                EquityCurvePoint(
                    timestamp=s.timestamp,
                    equity=s.balance,
                    cash=s.balance,
                    positions_value=0.0,  # TODO: Calculate from position snapshots
                )
                for s in snapshots
            ]
    except Exception as e:
        logger.error(f"Error fetching equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets", response_model=List[MarketResponse])
async def get_markets(active: bool = Query(True), limit: int = Query(50, le=200)):
    """Get available markets."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        markets = await state.agent.client.get_markets(active=active, limit=limit)

        return [
            MarketResponse(
                condition_id=m.condition_id,
                question=m.question,
                description=m.description,
                end_date=m.end_date,
                outcomes=m.outcomes,
                outcome_prices=m.outcome_prices,
                volume=m.volume,
                liquidity=m.liquidity,
                active=m.active,
            )
            for m in markets
        ]
    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/start")
async def start_agent():
    """Start the agent loop."""
    from probablyprofit.web.app import get_agent_state
    import asyncio

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    if state.agent.running:
        raise HTTPException(status_code=400, detail="Agent already running")

    # Start agent in background task
    asyncio.create_task(state.agent.run_loop())

    return {"status": "started"}


@router.post("/control/stop")
async def stop_agent():
    """Stop the agent loop."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    state.agent.running = False

    return {"status": "stopped"}


@router.post("/control/dry-run/{enabled}")
async def set_dry_run(enabled: bool):
    """Toggle dry-run mode."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    state.agent.dry_run = enabled

    return {"dry_run": enabled}
