"""
REST API Routes

All REST API endpoints for the dashboard.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from probablyprofit.web.api.models import (
    CorrelationGroup,
    EquityCurvePoint,
    ExposureResponse,
    HealthResponse,
    MarketResponse,
    PaperPortfolioResponse,
    PaperPositionResponse,
    PaperTradeResponse,
    PerformanceResponse,
    PositionExposure,
    StatusResponse,
    TradeResponse,
)

router = APIRouter(prefix="/api")


def api_error(status_code: int, message: str, code: str, details: str = None) -> HTTPException:
    """
    Create a consistent API error response.

    Args:
        status_code: HTTP status code
        message: User-friendly error message
        code: Error code for programmatic handling
        details: Technical details (optional)

    Returns:
        HTTPException with structured detail
    """
    detail = {"error": message, "code": code}
    if details:
        detail["details"] = details
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for monitoring systems.

    Returns:
        HealthResponse with overall status and component checks

    Status values:
        - healthy: All systems operational
        - degraded: Some issues but core functionality works
        - unhealthy: Critical systems failing
    """
    from probablyprofit.web.app import get_agent_state

    checks = {}
    overall_status = "healthy"

    # Check 1: Agent status
    state = get_agent_state()
    if state:
        agent_health = state.agent.get_health_status()
        checks["agent"] = {
            "status": "healthy" if agent_health["running"] else "stopped",
            "name": agent_health["name"],
            "loop_count": agent_health["loop_count"],
            "error_count": agent_health["error_count"],
            "consecutive_errors": agent_health["consecutive_errors"],
        }
        if agent_health["consecutive_errors"] > 3:
            checks["agent"]["status"] = "degraded"
            overall_status = "degraded"
        if agent_health["consecutive_errors"] > 8:
            checks["agent"]["status"] = "unhealthy"
            overall_status = "unhealthy"
    else:
        checks["agent"] = {"status": "not_initialized"}
        overall_status = "degraded"

    # Check 2: Database connectivity
    try:
        from probablyprofit.storage.database import get_db_manager

        db = get_db_manager()
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "unhealthy"

    # Check 3: Memory usage
    try:
        import psutil

        memory = psutil.virtual_memory()
        memory_pct = memory.percent
        checks["memory"] = {
            "status": (
                "healthy" if memory_pct < 80 else ("degraded" if memory_pct < 95 else "unhealthy")
            ),
            "percent_used": memory_pct,
        }
        if memory_pct >= 95:
            overall_status = "unhealthy"
        elif memory_pct >= 80 and overall_status == "healthy":
            overall_status = "degraded"
    except ImportError:
        checks["memory"] = {"status": "unknown", "error": "psutil not installed"}

    # Check 4: Last activity (was there recent trading activity?)
    if state and state.agent.memory.observations:
        last_obs = state.agent.memory.observations[-1]
        time_since_last = (datetime.now() - last_obs.timestamp).total_seconds()
        expected_interval = state.agent.loop_interval * 3  # Allow 3x the interval
        checks["activity"] = {
            "status": "healthy" if time_since_last < expected_interval else "degraded",
            "seconds_since_last_observation": time_since_last,
        }
        if time_since_last >= expected_interval and overall_status == "healthy":
            overall_status = "degraded"
    else:
        checks["activity"] = {"status": "no_data"}

    uptime = state.uptime_seconds if state else 0.0

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(),
        version="0.1.0",
        uptime_seconds=uptime,
        checks=checks,
    )


@router.get("/metrics")
async def get_metrics():
    """
    Get metrics in Prometheus format.

    Returns:
        Plain text metrics in Prometheus exposition format

    Usage:
        Configure Prometheus to scrape this endpoint:
        ```yaml
        scrape_configs:
          - job_name: 'probablyprofit'
            static_configs:
              - targets: ['localhost:8000']
            metrics_path: '/api/metrics'
        ```
    """
    from fastapi.responses import PlainTextResponse

    from probablyprofit.utils.metrics import get_metrics_registry

    registry = get_metrics_registry()
    return PlainTextResponse(
        content=registry.to_prometheus(),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/metrics/json")
async def get_metrics_json():
    """
    Get all metrics as JSON.

    Returns:
        Dictionary with counters, gauges, and histograms
    """
    from probablyprofit.utils.metrics import get_metrics_registry

    registry = get_metrics_registry()
    return registry.get_all_stats()


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current agent status."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

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
        raise api_error(
            500,
            "Unable to load trade history. Check that the database is accessible.",
            "TRADE_FETCH_ERROR",
            str(e),
        )


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance():
    """Get current performance metrics."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

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
                    equity=s.balance + s.total_exposure,
                    cash=s.balance,
                    positions_value=s.total_exposure,
                )
                for s in snapshots
            ]
    except Exception as e:
        logger.error(f"Error fetching equity curve: {e}")
        raise api_error(
            500,
            "Unable to load equity curve. Your trading history may be corrupted.",
            "EQUITY_FETCH_ERROR",
            str(e),
        )


@router.get("/markets", response_model=List[MarketResponse])
async def get_markets(active: bool = Query(True), limit: int = Query(50, le=200)):
    """Get available markets."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

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
        raise api_error(
            500,
            "Unable to load markets from Polymarket. Check your internet connection.",
            "MARKET_FETCH_ERROR",
            str(e),
        )


@router.post("/control/start")
async def start_agent():
    """Start the agent loop."""
    import asyncio

    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

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
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    state.agent.running = False

    return {"status": "stopped"}


@router.post("/control/dry-run/{enabled}")
async def set_dry_run(enabled: bool):
    """Toggle dry-run mode."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    state.agent.dry_run = enabled

    return {"dry_run": enabled}


@router.post("/emergency-stop")
async def emergency_stop(reason: str = Query("Remote kill switch activated via API")):
    """
    Emergency stop endpoint - activates the kill switch to halt all trading.

    This is a critical safety endpoint that immediately stops the trading bot.
    Use this in emergencies to prevent further losses.

    Args:
        reason: Reason for activating the kill switch

    Returns:
        Status confirmation with kill switch state
    """
    from probablyprofit.utils.killswitch import activate_kill_switch, is_kill_switch_active
    from probablyprofit.web.app import get_agent_state

    # Activate the kill switch
    activate_kill_switch(reason)

    # Also stop the agent if running
    state = get_agent_state()
    if state and state.agent.running:
        state.agent.running = False

    logger.warning(f"Emergency stop activated via API: {reason}")

    return {
        "status": "emergency_stop_activated",
        "kill_switch_active": is_kill_switch_active(),
        "reason": reason,
        "agent_stopped": not state.agent.running if state else None,
    }


@router.post("/emergency-stop/deactivate")
async def deactivate_emergency_stop():
    """
    Deactivate the emergency kill switch.

    Use this to resume trading after an emergency stop.
    The agent will need to be manually restarted after deactivation.

    Returns:
        Status confirmation
    """
    from probablyprofit.utils.killswitch import deactivate_kill_switch, is_kill_switch_active

    deactivate_kill_switch()

    logger.info("Emergency stop deactivated via API")

    return {
        "status": "emergency_stop_deactivated",
        "kill_switch_active": is_kill_switch_active(),
    }


@router.get("/emergency-stop/status")
async def get_emergency_stop_status():
    """
    Get current emergency stop / kill switch status.

    Returns:
        Kill switch status and reason if active
    """
    from probablyprofit.utils.killswitch import get_kill_switch

    kill_switch = get_kill_switch()
    is_active = kill_switch.is_active()
    reason = kill_switch.get_reason() if is_active else None

    return {
        "kill_switch_active": is_active,
        "reason": reason,
    }


@router.get("/exposure", response_model=ExposureResponse)
async def get_exposure():
    """Get portfolio exposure breakdown with correlation analysis."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    risk_manager = state.agent.risk_manager
    stats = risk_manager.get_stats()

    # Build position exposure list
    positions: List[PositionExposure] = []
    exposure_by_category: dict = {}
    warnings: List[str] = []

    # Get positions from risk manager
    for market_id, size in risk_manager.open_positions.items():
        # Try to get current market data
        try:
            # Get market question from last observation if available
            market_question = market_id[:50] + "..."
            current_price = 0.5  # Default
            entry_price = 0.5

            if state.agent.memory.observations:
                last_obs = state.agent.memory.observations[-1]
                for m in last_obs.markets:
                    if m.condition_id == market_id:
                        market_question = m.question
                        current_price = m.outcome_prices[0] if m.outcome_prices else 0.5
                        break

            value = size * current_price
            pnl = size * (current_price - entry_price)
            pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0

            # Detect correlation group
            correlation_group = _detect_correlation_group(market_question)

            # Track exposure by category
            if correlation_group:
                exposure_by_category[correlation_group] = (
                    exposure_by_category.get(correlation_group, 0) + value
                )

            positions.append(
                PositionExposure(
                    market_id=market_id,
                    market_question=market_question,
                    outcome="Yes",
                    size=size,
                    entry_price=entry_price,
                    current_price=current_price,
                    value=value,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    correlation_group=correlation_group,
                    has_trailing_stop=False,
                    stop_price=None,
                )
            )

        except Exception as e:
            logger.warning(f"Error processing position {market_id}: {e}")

    # Build correlation groups
    correlation_groups: List[CorrelationGroup] = []
    for group_name, total_exp in exposure_by_category.items():
        group_positions = [p for p in positions if p.correlation_group == group_name]
        risk_level = "low"
        if total_exp > risk_manager.limits.max_position_size * 2:
            risk_level = "high"
            warnings.append(f"High concentration in {group_name} (${total_exp:.2f})")
        elif total_exp > risk_manager.limits.max_position_size:
            risk_level = "medium"

        correlation_groups.append(
            CorrelationGroup(
                group_name=group_name,
                total_exposure=total_exp,
                positions_count=len(group_positions),
                markets=[p.market_id[:20] for p in group_positions],
                risk_level=risk_level,
            )
        )

    # Calculate risk metrics
    total_exposure = sum(p.value for p in positions)
    risk_metrics = {
        "concentration_ratio": (
            max(exposure_by_category.values()) / total_exposure if total_exposure > 0 else 0
        ),
        "position_count": len(positions),
        "avg_position_size": total_exposure / len(positions) if positions else 0,
        "max_position_size": max(p.value for p in positions) if positions else 0,
        "exposure_pct": (
            (total_exposure / stats["current_capital"]) * 100 if stats["current_capital"] > 0 else 0
        ),
        "daily_pnl": stats["daily_pnl"],
        "daily_loss_limit_used": abs(stats["daily_pnl"]) / risk_manager.limits.max_daily_loss * 100,
    }

    # Add warnings
    if risk_metrics["exposure_pct"] > 80:
        warnings.append(f"High portfolio exposure ({risk_metrics['exposure_pct']:.1f}%)")
    if risk_metrics["daily_loss_limit_used"] > 50:
        warnings.append(f"Daily loss limit {risk_metrics['daily_loss_limit_used']:.0f}% used")
    if len(positions) >= risk_manager.limits.max_positions - 1:
        warnings.append(
            f"Near max positions limit ({len(positions)}/{risk_manager.limits.max_positions})"
        )

    return ExposureResponse(
        total_value=stats["current_capital"],
        total_exposure=total_exposure,
        cash_balance=stats["current_capital"] - total_exposure,
        positions=positions,
        correlation_groups=correlation_groups,
        exposure_by_category=exposure_by_category,
        risk_metrics=risk_metrics,
        warnings=warnings,
    )


def _detect_correlation_group(question: str) -> Optional[str]:
    """Detect which correlation group a market belongs to."""
    question_lower = question.lower()

    correlation_keywords = {
        "politics_us": [
            "trump",
            "biden",
            "republican",
            "democrat",
            "election",
            "gop",
            "dnc",
            "congress",
            "senate",
        ],
        "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "memecoin"],
        "tech": ["apple", "google", "microsoft", "meta", "amazon", "nvidia", "ai", "openai"],
        "sports": ["nba", "nfl", "mlb", "super bowl", "championship", "playoffs", "world cup"],
        "economy": ["fed", "interest rate", "inflation", "gdp", "recession", "unemployment"],
        "entertainment": ["oscar", "grammy", "emmy", "movie", "box office", "netflix", "streaming"],
    }

    for group, keywords in correlation_keywords.items():
        if any(kw in question_lower for kw in keywords):
            return group

    return None


@router.get("/positions")
async def get_positions():
    """Get current open positions."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    risk_manager = state.agent.risk_manager
    positions = []

    for market_id, size in risk_manager.open_positions.items():
        positions.append(
            {
                "market_id": market_id,
                "size": size,
                "outcome": "Yes",
                "avg_price": 0.5,
                "current_price": 0.5,
                "pnl": 0.0,
            }
        )

    return positions


# ============ Paper Trading Endpoints ============


@router.get("/paper", response_model=PaperPortfolioResponse)
async def get_paper_portfolio():
    """Get paper trading portfolio status."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    # Check if paper trading is enabled
    paper_engine = getattr(state.agent, "paper_engine", None)
    if not paper_engine:
        return PaperPortfolioResponse(
            enabled=False,
            initial_capital=0,
            cash=0,
            positions_value=0,
            total_value=0,
            total_return=0,
            total_return_pct=0,
            realized_pnl=0,
            unrealized_pnl=0,
            total_fees=0,
            positions_count=0,
            trades_count=0,
            positions=[],
            recent_trades=[],
        )

    summary = paper_engine.get_portfolio_summary()
    positions = paper_engine.get_all_positions()
    trades = paper_engine.get_trade_history(limit=20)

    return PaperPortfolioResponse(
        enabled=True,
        initial_capital=summary["initial_capital"],
        cash=summary["cash"],
        positions_value=summary["positions_value"],
        total_value=summary["total_value"],
        total_return=summary["total_return"],
        total_return_pct=summary["total_return_pct"],
        realized_pnl=summary["realized_pnl"],
        unrealized_pnl=summary["unrealized_pnl"],
        total_fees=summary["total_fees"],
        positions_count=summary["positions_count"],
        trades_count=summary["trades_count"],
        positions=[
            PaperPositionResponse(
                market_id=p.market_id,
                market_question=p.market_question,
                side=p.side,
                size=p.size,
                avg_price=p.avg_price,
                current_price=p.current_price,
                value=p.value,
                unrealized_pnl=p.unrealized_pnl,
                unrealized_pnl_pct=p.unrealized_pnl_pct,
            )
            for p in positions
        ],
        recent_trades=[
            PaperTradeResponse(
                trade_id=t.trade_id,
                timestamp=t.timestamp,
                market_id=t.market_id,
                side=t.side,
                action=t.action,
                size=t.size,
                price=t.price,
                value=t.value,
                fees=t.fees,
            )
            for t in trades
        ],
    )


@router.post("/paper/reset")
async def reset_paper_portfolio(initial_capital: float = Query(10000.0)):
    """Reset paper trading portfolio."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    paper_engine = getattr(state.agent, "paper_engine", None)
    if not paper_engine:
        raise api_error(
            400,
            "Paper trading is not enabled. Run with --paper flag to enable.",
            "PAPER_TRADING_DISABLED",
        )

    paper_engine.reset(initial_capital=initial_capital)
    return {"status": "reset", "initial_capital": initial_capital}


@router.post("/paper/trade")
async def execute_paper_trade(
    market_id: str = Query(...),
    side: str = Query(...),
    action: str = Query(...),
    size: float = Query(...),
    price: float = Query(...),
    market_question: str = Query("Unknown market"),
):
    """Execute a manual paper trade."""
    from probablyprofit.web.app import get_agent_state

    state = get_agent_state()
    if not state:
        raise api_error(
            503,
            "Trading bot not running. Start it with 'probablyprofit run <strategy>'",
            "AGENT_NOT_INITIALIZED",
        )

    paper_engine = getattr(state.agent, "paper_engine", None)
    if not paper_engine:
        raise api_error(
            400,
            "Paper trading is not enabled. Run with --paper flag to enable.",
            "PAPER_TRADING_DISABLED",
        )

    trade = paper_engine.execute_trade(
        market_id=market_id,
        market_question=market_question,
        side=side,
        action=action,
        size=size,
        price=price,
    )

    if not trade:
        raise api_error(
            400,
            "Trade failed. Check that you have sufficient balance and valid parameters.",
            "TRADE_FAILED",
        )

    return {
        "status": "executed",
        "trade_id": trade.trade_id,
        "value": trade.value,
        "fees": trade.fees,
    }
