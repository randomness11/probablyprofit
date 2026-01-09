import asyncio
import os
import argparse
import sys
from dotenv import load_dotenv
from loguru import logger


# Add parent directory to path to allow importing this folder as 'probablyprofit' package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from probablyprofit.api.client import PolymarketClient
from probablyprofit.risk.manager import RiskManager
from probablyprofit.agent.openai_agent import OpenAIAgent
from probablyprofit.agent.gemini_agent import GeminiAgent
from probablyprofit.agent.anthropic_agent import AnthropicAgent
from probablyprofit.agent.ensemble import EnsembleAgent, VotingStrategy
from probablyprofit.agent.strategy import MeanReversionStrategy, NewsTradingStrategy, CustomStrategy


def parse_args():
    parser = argparse.ArgumentParser(description="ProbablyProfit: AI Trading Bot for Polymarket & Kalshi")

    # Platform selection
    parser.add_argument("--platform", type=str, choices=["polymarket", "kalshi"], default="polymarket",
                        help="Prediction market platform to use (default: polymarket)")

    parser.add_argument("--strategy", type=str, choices=["mean-reversion", "news", "custom"], default="mean-reversion",
                        help="Trading strategy to employ")
    parser.add_argument("--keywords", type=str, default="",
                        help="Comma-separated keywords for News/Custom strategy")
    parser.add_argument("--prompt-file", type=str, default="strategy.txt",
                        help="Path to custom strategy prompt file (for --strategy custom)")
    parser.add_argument("--agent", type=str, choices=["openai", "gemini", "anthropic", "ensemble"], default="openai",
                        help="AI provider to use (or 'ensemble' for multi-agent consensus)")
    parser.add_argument("--model", type=str, default="",
                        help="Specific model name (e.g. 'gpt-4o', 'o1-preview', 'gemini-1.5-pro')")
    parser.add_argument("--interval", type=int, default=60,
                        help="Loop interval in seconds")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without placing real trades (simulation mode)")
    
    # Intelligence Layer arguments
    parser.add_argument("--news", action="store_true",
                        help="Enable news context via Perplexity API (requires PERPLEXITY_API_KEY)")
    parser.add_argument("--top-markets", type=int, default=3,
                        help="Number of top markets to fetch news for (default: 3)")

    # Risk Management arguments
    parser.add_argument("--sizing", type=str, choices=["manual", "fixed_pct", "kelly", "confidence_based"],
                        default="manual", help="Position sizing method (default: manual)")
    parser.add_argument("--kelly-fraction", type=float, default=0.25,
                        help="Kelly fraction multiplier (default: 0.25)")

    # Backtesting arguments
    parser.add_argument("--backtest", action="store_true",
                        help="Run backtest simulation with synthetic data")
    parser.add_argument("--backtest-days", type=int, default=30,
                        help="Duration of backtest in days")
    
    # Ensemble-specific arguments
    parser.add_argument("--ensemble-agents", type=str, default="openai,gemini,anthropic",
                        help="Comma-separated list of agents for ensemble mode")
    parser.add_argument("--voting", type=str, choices=["majority", "weighted", "unanimous", "highest"],
                        default="majority", help="Voting strategy for ensemble mode")
    parser.add_argument("--min-agreement", type=int, default=2,
                        help="Minimum agents that must agree for ensemble decisions")
    
    return parser.parse_args()


def create_agent(
    agent_type: str,
    client: PolymarketClient,
    risk: "RiskManager",
    strategy_prompt: str,
    strategy,
    args,
) -> "BaseAgent":
    """Create a single agent based on type."""
    
    if agent_type == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY in .env")
        model = args.model if args.model else "gpt-4o"
        return OpenAIAgent(
            client, risk, api_key, strategy_prompt,
            model=model, loop_interval=args.interval,
            strategy=strategy, dry_run=args.dry_run
        )
        
    elif agent_type == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY in .env")
        model = args.model if args.model else "gemini-1.5-pro"
        return GeminiAgent(
            client, risk, api_key, strategy_prompt,
            model=model, loop_interval=args.interval,
            strategy=strategy, dry_run=args.dry_run
        )
        
    elif agent_type == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Missing ANTHROPIC_API_KEY in .env")
        model = args.model if args.model else "claude-sonnet-4-5-20250929"
        return AnthropicAgent(
            client, risk, api_key, strategy_prompt,
            model=model, loop_interval=args.interval
        )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


async def main():
    # 0. Load Config
    load_dotenv()
    args = parse_args()

    agent_label = args.agent
    if args.agent == "ensemble":
        agent_label = f"ensemble ({args.voting} voting)"

    logger.info(f"🚀 Starting ProbablyProfit Bot [Platform: {args.platform}] [Strategy: {args.strategy}] [Agent: {agent_label}]")

    # 0.5 Initialize Database (if persistence enabled)
    enable_persistence = os.getenv("ENABLE_PERSISTENCE", "true").lower() == "true"
    if enable_persistence:
        try:
            from probablyprofit.storage.database import initialize_database
            await initialize_database()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.warning(f"⚠️  Database initialization failed: {e}")
            logger.warning("Continuing without persistence...")

    # 1. Initialize Platform Client
    if args.platform == "polymarket":
        from probablyprofit.api.client import PolymarketClient
        client = PolymarketClient(
            private_key=os.getenv("PRIVATE_KEY")
        )
        logger.info("📊 Connected to Polymarket")

    elif args.platform == "kalshi":
        from probablyprofit.api.kalshi_client import KalshiClient
        client = KalshiClient(
            api_key_id=os.getenv("KALSHI_API_KEY_ID"),
            private_key_path=os.getenv("KALSHI_PRIVATE_KEY_PATH"),
            demo=os.getenv("KALSHI_DEMO", "false").lower() == "true"
        )
        logger.info("📊 Connected to Kalshi")

    else:
        logger.error(f"❌ Unknown platform: {args.platform}")
        return

    # 2. Risk Manager
    risk = RiskManager(initial_capital=float(os.getenv("INITIAL_CAPITAL", 1000.0)))
    
    # 3. Strategy Setup
    strategy = None
    if args.strategy == "mean-reversion":
        strategy = MeanReversionStrategy()
    elif args.strategy == "news":
        if not args.keywords:
            logger.error("❌ You must provide --keywords for news strategy")
            return
        keywords = [k.strip() for k in args.keywords.split(",")]
        strategy = NewsTradingStrategy(keywords=keywords)
    elif args.strategy == "custom":
        if not os.path.exists(args.prompt_file):
            logger.error(f"❌ Custom prompt file not found: {args.prompt_file}")
            print(f"💡 Tip: Create a {args.prompt_file} file with your strategy instructions.")
            return
        
        with open(args.prompt_file, "r") as f:
            prompt_text = f.read()
            
        keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []
        strategy = CustomStrategy(prompt_text=prompt_text, keywords=keywords)
        logger.info(f"Loaded Custom Strategy from {args.prompt_file}")
    else:
        logger.error("Unknown strategy.")
        return

    # 4. Agent Setup
    agent = None
    strategy_prompt = strategy.get_prompt()
    
    if args.agent == "ensemble":
        # Ensemble mode: create multiple agents
        ensemble_agent_types = [a.strip() for a in args.ensemble_agents.split(",")]
        logger.info(f"🤝 Creating ensemble with agents: {ensemble_agent_types}")
        
        agents = []
        for agent_type in ensemble_agent_types:
            try:
                a = create_agent(agent_type, client, risk, strategy_prompt, strategy, args)
                agents.append(a)
                logger.info(f"  ✅ {agent_type} agent created")
            except ValueError as e:
                logger.warning(f"  ⚠️  {agent_type}: {e}")
        
        if len(agents) < 2:
            logger.error("❌ Ensemble mode requires at least 2 working agents")
            await client.close()
            return
        
        # Map voting strategy
        voting_map = {
            "majority": VotingStrategy.MAJORITY,
            "weighted": VotingStrategy.WEIGHTED,
            "unanimous": VotingStrategy.UNANIMOUS,
            "highest": VotingStrategy.HIGHEST_CONFIDENCE,
        }
        voting = voting_map.get(args.voting, VotingStrategy.MAJORITY)
        
        agent = EnsembleAgent(
            client=client,
            risk_manager=risk,
            agents=agents,
            voting_strategy=voting,
            min_agreement=args.min_agreement,
            loop_interval=args.interval,
            strategy=strategy,
            dry_run=args.dry_run,
        )
    else:
        # Single agent mode
        try:
            agent = create_agent(args.agent, client, risk, strategy_prompt, strategy, args)
        except ValueError as e:
            logger.error(f"❌ {e}")
            await client.close()
            return
    
    # 4b. Wrap with Intelligence if enabled
    if args.news and agent:
        from probablyprofit.agent.intelligence import wrap_with_intelligence
        agent = wrap_with_intelligence(
            agent,
            enable_news=True,
            top_n_markets=args.top_markets,
        )
        if hasattr(agent, 'perplexity') and agent.perplexity:
            logger.info(f"📰 News intelligence enabled for top {args.top_markets} markets")

    # 4c. Apply Risk Settings
    if agent and hasattr(agent, "sizing_method"):
        agent.sizing_method = args.sizing
        agent.kelly_fraction = args.kelly_fraction
        if args.sizing != "manual":
            logger.info(f"⚖️  Auto-sizing enabled: {args.sizing} (Kelly fraction: {args.kelly_fraction})")

    # 5. Run Backtest or Live Loop
    try:
        if args.backtest:
            if not agent:
                logger.error("❌ No agent initialized for backtest")
                return

            from probablyprofit.backtesting.engine import BacktestEngine
            from probablyprofit.backtesting.data import MockDataGenerator
            
            logger.info(f"🔙 Starting Backtest Mode ({args.backtest_days} days)")
            
            # Generate synthetic data
            generator = MockDataGenerator()
            markets, timestamps = generator.generate_market_scenario(
                num_markets=5,
                days=args.backtest_days
            )
            
            # Run simulation
            engine = BacktestEngine(initial_capital=risk.initial_capital)
            result = await engine.run_backtest(agent, markets, timestamps)
            
            # Print Summary
            print("\n" + "="*50)
            print(f"📊 BACKTEST RESULTS ({result.start_time.date()} to {result.end_time.date()})")
            print("="*50)
            print(f"Return:         {result.total_return_pct:+.2%} (${result.total_return:+.2f})")
            print(f"Sharpe Ratio:   {result.sharpe_ratio:.2f}")
            print(f"Max Drawdown:   {result.max_drawdown:.2%}")
            print(f"Win Rate:       {result.win_rate:.1%}")
            print(f"Total Trades:   {result.total_trades}")
            print("="*50 + "\n")
            
        elif agent:
            # Check if web dashboard is enabled
            enable_web = os.getenv("ENABLE_WEB_DASHBOARD", "false").lower() == "true"
            web_port = int(os.getenv("WEB_DASHBOARD_PORT", "8000"))

            if enable_web:
                from probablyprofit.web.server import run_server_with_agent

                await run_server_with_agent(
                    agent=agent,
                    agent_type=args.agent,
                    strategy_name=args.strategy,
                    port=web_port,
                )
            else:
                await agent.run_loop()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user.")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
