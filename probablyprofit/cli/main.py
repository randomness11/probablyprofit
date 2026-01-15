#!/usr/bin/env python3
"""
ProbablyProfit CLI

The de facto way to run prediction market bots.

Usage:
    probablyprofit                                    # First time: setup wizard
    probablyprofit run "Buy underpriced markets"      # Inline strategy
    probablyprofit run -s strategy.txt                # File-based strategy
    probablyprofit markets                            # List markets
    probablyprofit status                             # Check status
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging

# Configure logging BEFORE any other imports to suppress debug logs
# This MUST happen before importing anything that uses loguru
from loguru import logger

# Disable all debug logging globally
logger.remove()  # Remove default stderr handler
logger.add(
    sys.stderr,
    format="{message}",
    level="WARNING",
    colorize=False,
)

# Also suppress other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import click
from rich import print as rprint
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from probablyprofit.config import (
    Config,
    get_quick_status,
    load_config,
    save_config,
    validate_api_key,
)

console = Console()

# Banner
BANNER = """
[bold blue]╔═══════════════════════════════════════════════════════════════╗[/bold blue]
[bold blue]║[/bold blue]              [bold white]🎲 ProbablyProfit[/bold white]                               [bold blue]║[/bold blue]
[bold blue]║[/bold blue]     [dim]Write strategy in English. AI does the rest.[/dim]          [bold blue]║[/bold blue]
[bold blue]╚═══════════════════════════════════════════════════════════════╝[/bold blue]
"""

QUICK_START = """
[bold]Quick Start:[/bold]

  [green]probablyprofit run "Buy YES when price < 0.15"[/green]   # Inline strategy
  [green]probablyprofit run -s my_strategy.txt[/green]            # From file
  [green]probablyprofit run --dry-run "..."[/green]               # Test mode (no real $)
  [green]probablyprofit markets[/green]                           # See active markets
  [green]probablyprofit status[/green]                            # Check configuration
"""


def show_banner():
    """Display the banner."""
    console.print(BANNER)


def show_quick_start():
    """Display quick start guide."""
    console.print(QUICK_START)


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.0", prog_name="probablyprofit")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output for debugging")
def cli(ctx, verbose):
    """
    ProbablyProfit - AI-powered prediction market trading.

    Write your strategy in plain English. Let AI trade for you.
    """
    # Store verbose in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Reconfigure logging if verbose
    if verbose:
        logger.remove()
        logger.add(
            sys.stderr,
            format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
            level="DEBUG",
            colorize=True,
        )

    if ctx.invoked_subcommand is None:
        # No subcommand - check if configured
        config = load_config()

        show_banner()

        if not config.is_configured:
            console.print("[yellow]Welcome! Let's get you set up.[/yellow]\n")
            ctx.invoke(setup)
        else:
            # Show status and quick start
            agents = config.get_available_agents()
            best = config.get_best_agent()

            console.print(f"[green]✓[/green] Configured with: [bold]{', '.join(agents)}[/bold]")
            if config.has_wallet():
                console.print(f"[green]✓[/green] Wallet connected ({config.platform})")
            else:
                console.print("[yellow]○[/yellow] No wallet (read-only mode)")

            console.print()
            show_quick_start()


@cli.command()
@click.option("--reconfigure", "-r", is_flag=True, help="Reconfigure from scratch")
def setup(reconfigure: bool = False):
    """
    Interactive setup wizard.

    Guides you through configuring API keys and wallet.
    """
    config = load_config() if not reconfigure else Config()

    if not reconfigure:
        show_banner()

    console.print("[bold]Let's set up ProbablyProfit![/bold]\n")

    # Step 1: AI Provider
    console.print("[bold cyan]Step 1: AI Provider[/bold cyan]")
    console.print("Choose at least one AI to power your trading decisions.\n")

    ai_choices = [
        ("OpenAI", "openai", "GPT-4o - Great all-around performance"),
        ("Anthropic", "anthropic", "Claude - Advanced reasoning"),
        ("Google", "google", "Gemini - Fast and cost-effective"),
    ]

    for i, (name, key, desc) in enumerate(ai_choices, 1):
        current = getattr(config, f"{key}_api_key")
        status = "[green]✓[/green]" if current else "[dim]○[/dim]"
        console.print(f"  {status} [{i}] {name}: {desc}")

    console.print()

    # Ask which to configure
    while True:
        choice = Prompt.ask(
            "Which AI would you like to configure? (1/2/3, or 'skip' if already set)",
            default="1" if not config.is_configured else "skip",
        )

        if choice.lower() == "skip":
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ai_choices):
                name, provider, _ = ai_choices[idx]

                # Get and validate API key with retry loop
                while True:
                    key = Prompt.ask(f"Enter your {name} API key", password=True)

                    if not key:
                        console.print("[dim]Skipped.[/dim]\n")
                        break

                    # Validate
                    with console.status(f"[bold]Validating {name} API key...[/bold]"):
                        valid = validate_api_key(provider, key)

                    if valid:
                        setattr(config, f"{provider}_api_key", key)
                        console.print(f"[green]✓ {name} configured successfully![/green]\n")
                        break
                    else:
                        console.print(f"[red]✗ Invalid API key.[/red]")
                        if not Confirm.ask("Try again?", default=True):
                            console.print("[dim]Skipped.[/dim]\n")
                            break

                # Ask if they want to add another
                if not Confirm.ask("Add another AI provider?", default=False):
                    break
        except (ValueError, IndexError):
            console.print("[red]Please enter 1, 2, 3, or 'skip'[/red]")

    # Check we have at least one AI
    if not config.get_available_agents():
        console.print("[red]You need at least one AI provider to continue.[/red]")
        console.print("Get API keys from:")
        console.print("  • OpenAI: https://platform.openai.com/api-keys")
        console.print("  • Anthropic: https://console.anthropic.com/")
        console.print("  • Google: https://makersuite.google.com/app/apikey")
        return

    # Explain trading modes
    console.print("\n[bold cyan]Trading Modes[/bold cyan]")
    console.print(
        "  [yellow]Dry-run[/yellow]  - Simulate trades on live market data (safe for testing)"
    )
    console.print("  [cyan]Paper[/cyan]    - Virtual portfolio with simulated money")
    console.print("  [red]Live[/red]     - Real money trades (requires wallet + confirmation)")
    console.print("[dim]Switch modes with --dry-run, --paper, or --live flags[/dim]\n")

    # Step 2: Wallet (optional)
    console.print("[bold cyan]Step 2: Wallet Configuration (Optional)[/bold cyan]")
    console.print("Connect a wallet to enable [red]live trading[/red].")
    console.print("[dim]Note: Polymarket API keys are auto-derived from your private key.[/dim]")
    console.print("[dim]You don't need to manually create them on Polymarket's website.[/dim]\n")

    if Confirm.ask("Connect a Polymarket wallet?", default=False):
        console.print("\n[dim]Your private key is stored locally and never sent anywhere.[/dim]")
        pk = Prompt.ask("Enter your Ethereum private key (starts with 0x)", password=True)

        if pk:
            config.private_key = pk
            config.platform = "polymarket"
            console.print("[green]✓ Wallet connected![/green]")

            # Try to derive Polymarket API credentials
            try:
                from py_clob_client.client import ClobClient

                with console.status("[bold]Deriving Polymarket API credentials...[/bold]"):
                    client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
                    creds = client.create_or_derive_api_key()

                # Store in environment for this session
                os.environ["POLYMARKET_API_KEY"] = creds.api_key
                os.environ["POLYMARKET_API_SECRET"] = creds.api_secret
                os.environ["POLYMARKET_API_PASSPHRASE"] = creds.api_passphrase

                console.print("[green]✓ Polymarket API credentials derived![/green]")
            except Exception as e:
                console.print(f"[yellow]Could not derive Polymarket credentials: {e}[/yellow]")
                console.print("[dim]You may need to set them manually in .env[/dim]")
    else:
        console.print("[dim]Wallet skipped. Available modes without a wallet:[/dim]")
        console.print("  [cyan]Paper[/cyan]:   probablyprofit run -s strategy.txt --paper")
        console.print("  [yellow]Dry-run[/yellow]: probablyprofit run -s strategy.txt --dry-run")
        console.print("  [dim]Read-only: Fetch and analyze markets without trading[/dim]\n")

    # Step 3: Preferences
    console.print("\n[bold cyan]Step 3: Preferences[/bold cyan]\n")

    # Default mode
    config.dry_run = Confirm.ask("Start in safe mode (dry-run, no real trades)?", default=True)

    # Set preferred agent
    agents = config.get_available_agents()
    if len(agents) > 1:
        console.print(f"\nYou have multiple AI providers: {', '.join(agents)}")
        preferred = Prompt.ask(
            "Which should be the default?", choices=agents + ["auto"], default="auto"
        )
        config.preferred_agent = preferred
    elif agents:
        config.preferred_agent = agents[0]

    # Save configuration
    save_config(config)

    console.print("\n[bold green]✓ Setup complete![/bold green]\n")

    # Show configuration summary
    console.print("[bold]Configuration Summary:[/bold]")
    agents = config.get_available_agents()
    console.print(f"  AI Providers:  {', '.join(agents) if agents else '[red]none[/red]'}")
    console.print(f"  Default Agent: {config.preferred_agent or 'auto'}")
    wallet_status = "[green]connected[/green]" if config.private_key else "[dim]not connected[/dim]"
    console.print(f"  Wallet:        {wallet_status}")
    mode = "[yellow]dry-run (safe)[/yellow]" if config.dry_run else "[red]live[/red]"
    console.print(f"  Default Mode:  {mode}")
    console.print()
    console.print("[dim]Saved to ~/.probablyprofit/[/dim]\n")

    show_quick_start()


@cli.command()
@click.argument("strategy", required=False)
@click.option("--strategy-file", "-s", type=click.Path(exists=True), help="Path to strategy file")
@click.option(
    "--dry-run", "-d", is_flag=True, default=None, help="Simulate trades without real money"
)
@click.option("--live", is_flag=True, help="Enable live trading (overrides dry-run)")
@click.option("--confirm-live", is_flag=True, help="Confirm live trading (required for live mode)")
@click.option("--skip-preflight", is_flag=True, help="Skip preflight checks (not recommended)")
@click.option(
    "--agent",
    "-a",
    type=click.Choice(["openai", "anthropic", "google", "auto"]),
    default="auto",
    help="AI agent to use",
)
@click.option("--interval", "-i", type=int, default=60, help="Loop interval in seconds")
@click.option("--paper", "-p", is_flag=True, help="Paper trading with virtual money")
@click.option(
    "--paper-capital", type=float, default=10000, help="Starting capital for paper trading"
)
@click.option("--news", is_flag=True, help="Enable news context (requires Perplexity API)")
@click.option("--once", is_flag=True, help="Run once and exit (don't loop)")
@click.option("--stream", is_flag=True, default=True, help="Stream AI thinking in real-time")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
@click.option("--kelly", is_flag=True, help="Enable Kelly criterion position sizing")
@click.option(
    "--sizing",
    type=click.Choice(["manual", "kelly", "confidence", "dynamic"]),
    default="manual",
    help="Position sizing method",
)
def run(
    strategy: Optional[str],
    strategy_file: Optional[str],
    dry_run: Optional[bool],
    live: bool,
    confirm_live: bool,
    skip_preflight: bool,
    agent: str,
    interval: int,
    paper: bool,
    paper_capital: float,
    news: bool,
    once: bool,
    stream: bool,
    no_stream: bool,
    kelly: bool,
    sizing: str,
):
    """
    Start the trading bot.

    STRATEGY can be provided inline or via --strategy-file.

    Examples:

        probablyprofit run "Buy YES when price < 0.15"

        probablyprofit run -s my_strategy.txt

        probablyprofit run --dry-run "Buy underpriced markets"

        probablyprofit run --paper "Momentum trading on high volume"
    """
    config = load_config()

    # Check if configured
    if not config.is_configured:
        console.print("[red]Not configured yet![/red]")
        console.print("Run [bold]probablyprofit setup[/bold] first.\n")
        return

    show_banner()

    # Determine strategy
    strategy_prompt = None

    if strategy:
        # Inline strategy
        strategy_prompt = strategy
        console.print(
            f"[bold]Strategy:[/bold] {strategy[:60]}{'...' if len(strategy) > 60 else ''}\n"
        )

    elif strategy_file:
        # File-based strategy
        with open(strategy_file) as f:
            strategy_prompt = f.read()
        console.print(f"[bold]Strategy:[/bold] {strategy_file}\n")

    else:
        # Check for default strategy.txt
        if Path("strategy.txt").exists():
            with open("strategy.txt") as f:
                strategy_prompt = f.read()
            console.print("[bold]Strategy:[/bold] strategy.txt (default)\n")
        else:
            # Ask for inline strategy
            console.print("[yellow]No strategy provided.[/yellow]")
            console.print("Enter your strategy (or Ctrl+C to cancel):\n")
            strategy_prompt = Prompt.ask("[bold]Strategy[/bold]")
            console.print()

    if not strategy_prompt:
        console.print("[red]Strategy is required.[/red]")
        return

    # Determine mode
    if live:
        is_dry_run = False
    elif dry_run is not None:
        is_dry_run = dry_run
    else:
        is_dry_run = config.dry_run  # Use config default

    # Run preflight checks (unless skipped)
    if not skip_preflight:
        console.print("[bold]Running preflight checks...[/bold]\n")
        try:
            from probablyprofit.utils.preflight import run_preflight_checks_sync

            report = run_preflight_checks_sync(dry_run=is_dry_run)

            # Show results
            for check in report.checks:
                if check.status.value == "pass":
                    console.print(f"  [green]\u2713[/green] {check.name}: {check.message}")
                elif check.status.value == "fail":
                    console.print(f"  [red]\u2717[/red] {check.name}: {check.message}")
                elif check.status.value == "warn":
                    console.print(f"  [yellow]![/yellow] {check.name}: {check.message}")
                else:
                    console.print(f"  [dim]-[/dim] {check.name}: {check.message}")

            console.print()

            if not report.passed:
                console.print(
                    "[red]Preflight checks FAILED. Fix the issues above before trading.[/red]"
                )
                return
        except ImportError:
            console.print("[yellow]Preflight checks not available, skipping...[/yellow]\n")

    # Live trading confirmation
    if not is_dry_run:
        console.print("[bold red]WARNING: LIVE TRADING MODE[/bold red]")
        console.print("[red]You are about to trade with REAL MONEY.[/red]\n")

        if not confirm_live:
            console.print(
                "[yellow]To enable live trading, you must pass --confirm-live flag.[/yellow]"
            )
            console.print('Example: probablyprofit run --live --confirm-live "Your strategy"\n')
            return

        # Double confirmation via interactive prompt
        confirmation = Prompt.ask(
            "[bold red]Type 'YES' to confirm live trading[/bold red]", default="no"
        )

        if confirmation != "YES":
            console.print("[yellow]Live trading cancelled.[/yellow]")
            return

        console.print("[green]Live trading confirmed. Be careful![/green]\n")

        # Log to audit file
        import time

        audit_file = Path.home() / ".probablyprofit" / "live_trading.log"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_file, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Live trading started\n")

    # Determine agent
    if agent == "auto":
        selected_agent = config.get_best_agent()
    else:
        selected_agent = agent

    if not selected_agent:
        console.print("[red]No AI provider available.[/red]")
        console.print("Run [bold]probablyprofit setup[/bold] to configure one.")
        return

    api_key = config.get_api_key_for_agent(selected_agent)
    model = config.get_model_for_agent(selected_agent)

    # Display configuration
    mode_str = "[yellow]DRY RUN[/yellow]" if is_dry_run else "[red]LIVE[/red]"
    if paper:
        mode_str = f"[cyan]PAPER (${paper_capital:,.0f})[/cyan]"

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    table.add_row("Mode", mode_str)
    table.add_row("Agent", f"{selected_agent} ({model})")
    table.add_row("Interval", f"{interval}s")
    if config.has_wallet() and not is_dry_run and not paper:
        table.add_row("Wallet", "[green]Connected[/green]")
    table.add_row("News", "[green]Enabled[/green]" if news else "[dim]Disabled[/dim]")

    console.print(table)
    console.print()

    # Confirm if live
    if not is_dry_run and not paper:
        if not Confirm.ask("[bold red]You're about to trade with REAL money. Continue?[/bold red]"):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Run the bot
    async def _run():
        from probablyprofit.agent.strategy import CustomStrategy
        from probablyprofit.api.client import PolymarketClient
        from probablyprofit.risk.manager import RiskManager

        # Import the right agent
        if selected_agent == "openai":
            from probablyprofit.agent.openai_agent import OpenAIAgent as AgentClass
        elif selected_agent == "anthropic":
            from probablyprofit.agent.anthropic_agent import AnthropicAgent as AgentClass
        else:
            from probablyprofit.agent.gemini_agent import GeminiAgent as AgentClass

        # Initialize client
        client = PolymarketClient(private_key=config.private_key)

        # Initialize risk manager
        risk = RiskManager(initial_capital=config.initial_capital)

        # Create strategy
        strategy_obj = CustomStrategy(prompt_text=strategy_prompt)

        # Create agent with correct parameter name for each provider
        agent_kwargs = {
            "client": client,
            "risk_manager": risk,
            "strategy_prompt": strategy_prompt,
            "model": model,
            "loop_interval": interval,
            "strategy": strategy_obj,
            "dry_run": is_dry_run or paper,
        }

        # Each agent has a different parameter name for API key
        if selected_agent == "openai":
            agent_kwargs["openai_api_key"] = api_key
        elif selected_agent == "anthropic":
            agent_kwargs["anthropic_api_key"] = api_key
        elif selected_agent == "google":
            agent_kwargs["google_api_key"] = api_key

        agent_instance = AgentClass(**agent_kwargs)

        # Enable smart position sizing
        if kelly or sizing == "kelly":
            agent_instance.sizing_method = "kelly"
            agent_instance.kelly_fraction = 0.25  # Quarter Kelly for safety
            console.print("[cyan]📊 Kelly criterion sizing enabled (quarter Kelly)[/cyan]")
        elif sizing == "confidence":
            agent_instance.sizing_method = "confidence_based"
            console.print("[cyan]📊 Confidence-based sizing enabled[/cyan]")
        elif sizing == "dynamic":
            agent_instance.sizing_method = "dynamic"
            console.print("[cyan]📊 Dynamic sizing enabled[/cyan]")

        # Setup paper trading if enabled
        if paper:
            from probablyprofit.trading.paper import PaperTradingEngine

            paper_engine = PaperTradingEngine(
                initial_capital=paper_capital,
                fee_rate=0.02,
            )
            agent_instance.paper_engine = paper_engine
            console.print(f"[cyan]Paper trading initialized with ${paper_capital:,.2f}[/cyan]\n")

        # Enable news if requested
        if news:
            from probablyprofit.agent.intelligence import wrap_with_intelligence

            agent_instance = wrap_with_intelligence(agent_instance, enable_news=True)
            console.print("[dim]News intelligence enabled[/dim]\n")

        console.print("[bold green]Starting bot...[/bold green]\n")

        # Determine if we should stream
        use_streaming = stream and not no_stream and once and selected_agent == "anthropic"

        try:
            if once:
                # Single run
                with console.status("[bold]Fetching market data...[/bold]"):
                    observation = await agent_instance.observe()

                console.print(f"[dim]Found {len(observation.markets)} markets to analyze[/dim]\n")

                if use_streaming:
                    # Streaming mode - show AI thinking in real-time
                    console.print("[bold cyan]AI Analysis:[/bold cyan]\n")

                    # Create a live display for streaming
                    from rich.live import Live
                    from rich.text import Text

                    output_text = Text()

                    def on_chunk(chunk: str):
                        # Print each chunk as it arrives
                        console.print(chunk, end="")

                    # Use streaming decision
                    decision = agent_instance.decide_streaming(observation, on_chunk=on_chunk)
                    console.print("\n")  # Newline after streaming
                else:
                    # Non-streaming mode
                    with console.status("[bold]AI is analyzing markets...[/bold]"):
                        decision = await agent_instance.decide(observation)

                # Show decision summary
                console.print(f"\n[bold]Decision:[/bold] {decision.action.upper()}")
                if decision.market_id:
                    # Look up market name
                    market_name = decision.market_id[:40] + "..."
                    for m in observation.markets:
                        if m.condition_id == decision.market_id:
                            market_name = m.question[:60] + ("..." if len(m.question) > 60 else "")
                            break
                    console.print(f"  Market: [cyan]{market_name}[/cyan]")
                    console.print(f"  Outcome: {decision.outcome}")
                    console.print(f"  Size: ${decision.size:.2f}")
                    console.print(f"  Confidence: {decision.confidence:.0%}")
                if not use_streaming:
                    console.print(f"  Reasoning: {decision.reasoning[:200]}...")

                # Execute the decision
                if decision.action != "hold":
                    # Always call act() - it handles dry run internally and shows market names
                    await agent_instance.act(decision)
                    if not is_dry_run and not paper:
                        console.print("[green]Trade executed![/green]")
            else:
                # Continuous loop
                await agent_instance.run_loop()
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped by user.[/yellow]")
        finally:
            await client.close()

    asyncio.run(_run())


@cli.command()
@click.option("--limit", "-l", type=int, default=10, help="Number of markets to show")
@click.option("--search", "-q", type=str, help="Search query to filter markets")
def markets(limit: int, search: Optional[str]):
    """
    List active prediction markets.

    Examples:

        probablyprofit markets

        probablyprofit markets --limit 20

        probablyprofit markets -q "bitcoin"
    """

    async def _markets():
        from probablyprofit.api.client import PolymarketClient

        config = load_config()
        client = PolymarketClient(private_key=config.private_key)

        try:
            with console.status("[bold]Fetching markets...[/bold]"):
                markets_list = await client.get_markets(active=True, limit=50)

            if search:
                search_lower = search.lower()
                markets_list = [
                    m
                    for m in markets_list
                    if search_lower in m.question.lower()
                    or (m.description and search_lower in m.description.lower())
                ]

            markets_list = markets_list[:limit]

            if not markets_list:
                console.print("[yellow]No markets found.[/yellow]")
                return

            console.print(f"\n[bold]📊 Active Markets ({len(markets_list)})[/bold]\n")

            table = Table(show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("Market", width=50)
            table.add_column("YES", justify="right", width=6)
            table.add_column("NO", justify="right", width=6)
            table.add_column("Volume", justify="right", width=12)

            for i, m in enumerate(markets_list, 1):
                # Format prices
                yes_price = m.outcome_prices[0] if m.outcome_prices else 0.5
                no_price = m.outcome_prices[1] if len(m.outcome_prices) > 1 else 1 - yes_price

                # Truncate question
                q = m.question[:47] + "..." if len(m.question) > 50 else m.question

                # Color based on price
                yes_color = "green" if yes_price < 0.3 else ("red" if yes_price > 0.7 else "white")
                no_color = "green" if no_price < 0.3 else ("red" if no_price > 0.7 else "white")

                table.add_row(
                    str(i),
                    q,
                    f"[{yes_color}]{yes_price:.0%}[/{yes_color}]",
                    f"[{no_color}]{no_price:.0%}[/{no_color}]",
                    f"${m.volume:,.0f}",
                )

            console.print(table)
            console.print()

        finally:
            await client.close()

    asyncio.run(_markets())


@cli.command()
def status():
    """
    Show current configuration status.
    """
    show_banner()

    config = load_config()
    status_info = get_quick_status()

    console.print("[bold]Configuration Status[/bold]\n")

    # AI Providers
    agents = config.get_available_agents()
    if agents:
        console.print(f"[green]✓[/green] AI Providers: {', '.join(agents)}")
        best = config.get_best_agent()
        console.print(f"  [dim]Default: {best} ({config.get_model_for_agent(best)})[/dim]")
    else:
        console.print("[red]✗[/red] No AI providers configured")

    # Wallet
    if config.has_wallet():
        console.print(f"[green]✓[/green] Wallet: Connected ({config.platform})")
    else:
        console.print("[yellow]○[/yellow] Wallet: Not connected (read-only mode)")

    # Trading mode
    mode = "Dry Run (safe)" if config.dry_run else "Live"
    color = "yellow" if config.dry_run else "red"
    console.print(f"[{color}]○[/{color}] Mode: {mode}")

    # Intelligence
    if config.perplexity_api_key:
        console.print("[green]✓[/green] News: Perplexity configured")

    console.print()

    # Show config location
    console.print(f"[dim]Config: ~/.probablyprofit/[/dim]")
    console.print()

    if not config.is_configured:
        console.print("Run [bold]probablyprofit setup[/bold] to configure.\n")


@cli.command()
def balance():
    """
    Check your wallet balance.
    """

    async def _balance():
        config = load_config()

        if not config.has_wallet():
            console.print("[yellow]No wallet configured.[/yellow]")
            console.print("Run [bold]probablyprofit setup[/bold] to connect a wallet.")
            return

        from probablyprofit.api.client import PolymarketClient

        client = PolymarketClient(private_key=config.private_key)

        try:
            with console.status("[bold]Fetching balance...[/bold]"):
                bal = await client.get_balance()

            console.print(f"\n[bold]💰 Balance: [green]${bal:,.2f} USDC[/green][/bold]\n")
        finally:
            await client.close()

    asyncio.run(_balance())


@cli.command()
def positions():
    """
    Show your open positions.
    """

    async def _positions():
        config = load_config()

        if not config.has_wallet():
            console.print("[yellow]No wallet configured.[/yellow]")
            return

        from probablyprofit.api.client import PolymarketClient

        client = PolymarketClient(private_key=config.private_key)

        try:
            with console.status("[bold]Fetching positions...[/bold]"):
                pos = await client.get_positions()

            if not pos:
                console.print("\n[dim]No open positions.[/dim]\n")
                return

            console.print(f"\n[bold]📈 Open Positions ({len(pos)})[/bold]\n")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Market")
            table.add_column("Side")
            table.add_column("Size", justify="right")
            table.add_column("Entry", justify="right")
            table.add_column("P&L", justify="right")

            for p in pos:
                pnl_color = "green" if p.pnl >= 0 else "red"
                table.add_row(
                    p.market_id[:30] + "...",
                    p.outcome,
                    f"{p.size:.2f}",
                    f"${p.avg_price:.2f}",
                    f"[{pnl_color}]${p.pnl:+.2f}[/{pnl_color}]",
                )

            console.print(table)
            console.print()

        finally:
            await client.close()

    asyncio.run(_positions())


@cli.command()
@click.option("--port", "-p", type=int, default=8000, help="Port for dashboard")
def dashboard(port: int):
    """
    Launch the web dashboard.
    """
    console.print(f"[bold]Starting dashboard on http://localhost:{port}[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        import uvicorn

        from probablyprofit.web.app import create_app

        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except ImportError:
        console.print("[red]uvicorn not installed.[/red]")
        console.print("Run: pip install uvicorn")


@cli.command()
@click.option("--strategy-file", "-s", type=click.Path(exists=True), required=True)
@click.option("--days", "-d", type=int, default=30)
def backtest(strategy_file: str, days: int):
    """
    Backtest a strategy on historical data.

    Example:

        probablyprofit backtest -s my_strategy.txt --days 60
    """

    async def _backtest():
        from probablyprofit.agent.mock_agent import MockAgent
        from probablyprofit.backtesting.data import MockDataGenerator
        from probablyprofit.backtesting.engine import BacktestEngine
        from probablyprofit.risk.manager import RiskManager

        config = load_config()

        with open(strategy_file) as f:
            strategy_text = f.read()

        console.print(f"[bold]Running backtest ({days} days)[/bold]\n")
        console.print(f"Strategy: {strategy_file}\n")

        with console.status("[bold]Generating market data...[/bold]"):
            generator = MockDataGenerator()
            markets_data, timestamps = generator.generate_market_scenario(num_markets=5, days=days)

        with console.status("[bold]Running simulation...[/bold]"):
            risk = RiskManager(initial_capital=config.initial_capital)
            agent = MockAgent(None, risk)
            engine = BacktestEngine(initial_capital=config.initial_capital)
            result = await engine.run_backtest(agent, markets_data, timestamps)

        # Results
        console.print("\n[bold]📊 Backtest Results[/bold]\n")

        ret_color = "green" if result.total_return >= 0 else "red"

        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Return", f"[{ret_color}]{result.total_return_pct:+.2%}[/{ret_color}]")
        table.add_row("Sharpe Ratio", f"{result.sharpe_ratio:.2f}")
        table.add_row("Max Drawdown", f"[red]{result.max_drawdown:.2%}[/red]")
        table.add_row("Win Rate", f"{result.win_rate:.1%}")
        table.add_row("Total Trades", str(result.total_trades))

        console.print(table)
        console.print()

    asyncio.run(_backtest())


@cli.command(name="create-strategy")
@click.argument("output", default="strategy.txt")
def create_strategy(output: str):
    """
    Interactive strategy builder.

    Helps you write a trading strategy step by step.
    """
    show_banner()

    console.print("[bold]Strategy Builder[/bold]\n")
    console.print("Let's build your trading strategy step by step.\n")

    # Goal
    goal = Prompt.ask(
        "[bold]1. What's your goal?[/bold]\n"
        "   [dim](e.g., 'Find undervalued markets', 'Trade momentum', 'Bet on politics')[/dim]\n"
        "   Goal"
    )

    # Entry rules
    console.print()
    entry = Prompt.ask(
        "[bold]2. When should the bot BUY?[/bold]\n"
        "   [dim](e.g., 'When price < 0.20 and volume > 10000')[/dim]\n"
        "   Buy when"
    )

    # Exit/avoid rules
    console.print()
    avoid = Prompt.ask(
        "[bold]3. What should it AVOID?[/bold]\n"
        "   [dim](e.g., 'Markets with low liquidity', 'Prices near 50/50')[/dim]\n"
        "   Avoid",
        default="low liquidity markets",
    )

    # Position size
    console.print()
    size = Prompt.ask(
        "[bold]4. How much per trade?[/bold]\n"
        "   [dim](e.g., '$10', '5% of capital')[/dim]\n"
        "   Size",
        default="$10",
    )

    # Risk tolerance
    console.print()
    risk_level = Prompt.ask(
        "[bold]5. Risk tolerance?[/bold]",
        choices=["conservative", "moderate", "aggressive"],
        default="moderate",
    )

    # Build the strategy
    confidence_map = {
        "conservative": "Only trade with high confidence (>0.8). Prioritize capital preservation.",
        "moderate": "Trade with moderate confidence (>0.6). Balance risk and reward.",
        "aggressive": "Trade on reasonable signals (>0.5). Maximize opportunities.",
    }

    strategy_text = f"""You are a trading bot for Polymarket prediction markets.

GOAL: {goal}

ENTRY RULES:
- {entry}
- Focus on markets with good volume and liquidity
- Look for mispriced opportunities where your analysis differs from market price

AVOID:
- {avoid}
- Markets about to resolve (unless you have high confidence)
- Already efficient/fairly priced markets

POSITION SIZING:
- Trade size: {size}
- Never exceed risk limits

RISK MANAGEMENT:
{confidence_map[risk_level]}

When analyzing each market:
1. Assess the true probability based on available information
2. Compare to market price to find edge
3. Only trade when you have a clear thesis
4. Explain your reasoning clearly
"""

    # Save
    with open(output, "w") as f:
        f.write(strategy_text)

    console.print(f"\n[green]✓ Strategy saved to {output}[/green]\n")
    console.print("[bold]Preview:[/bold]")
    console.print(Panel(strategy_text, border_style="dim"))
    console.print()
    console.print(f"Run it with: [bold]probablyprofit run -s {output}[/bold]")
    console.print()


@cli.command(name="completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str):
    """
    Generate shell completion script.

    Install completions:

        # Bash
        probablyprofit completion bash >> ~/.bashrc

        # Zsh
        probablyprofit completion zsh >> ~/.zshrc

        # Fish
        probablyprofit completion fish > ~/.config/fish/completions/probablyprofit.fish
    """
    import click.shell_completion as sc

    # Get the completion class for the shell
    shell_cls = {
        "bash": sc.BashComplete,
        "zsh": sc.ZshComplete,
        "fish": sc.FishComplete,
    }.get(shell)

    if shell_cls:
        comp = shell_cls(cli, {}, "probablyprofit", "_PROBABLYPROFIT_COMPLETE")
        console.print(comp.source())
    else:
        console.print(f"[red]Unknown shell: {shell}[/red]")


@cli.command(name="emergency-stop")
@click.option("--reason", "-r", default="Manual emergency stop", help="Reason for stop")
def emergency_stop(reason: str):
    """
    Activate emergency kill switch to halt all trading.

    This immediately stops all trading activity. Use when you need
    to halt trading due to market conditions, bugs, or emergencies.

    Example:

        probablyprofit emergency-stop --reason "Market crash"
    """
    console.print("[bold red]EMERGENCY STOP[/bold red]\n")

    try:
        from probablyprofit.utils.killswitch import activate_kill_switch, get_kill_switch

        kill_switch = get_kill_switch()

        if kill_switch.is_active():
            console.print(
                f"[yellow]Kill switch already active: {kill_switch.get_reason()}[/yellow]"
            )
        else:
            activate_kill_switch(reason)
            console.print(f"[red]Kill switch ACTIVATED[/red]")
            console.print(f"Reason: {reason}\n")
            console.print("All trading has been halted.")
            console.print("To resume, run: probablyprofit resume-trading")

    except ImportError:
        console.print("[red]Kill switch module not available.[/red]")


@cli.command(name="resume-trading")
def resume_trading():
    """
    Deactivate kill switch and resume trading.

    Use this after resolving the issue that triggered the emergency stop.
    """
    console.print("[bold]Resume Trading[/bold]\n")

    try:
        from probablyprofit.utils.killswitch import deactivate_kill_switch, get_kill_switch

        kill_switch = get_kill_switch()

        if not kill_switch.is_active():
            console.print("[green]Kill switch is not active. Trading already enabled.[/green]")
        else:
            reason = kill_switch.get_reason()
            console.print(f"[yellow]Kill switch was active: {reason}[/yellow]")

            if Confirm.ask("Are you sure you want to resume trading?", default=False):
                deactivate_kill_switch()
                console.print("[green]Kill switch DEACTIVATED. Trading can resume.[/green]")
            else:
                console.print("[yellow]Cancelled. Kill switch remains active.[/yellow]")

    except ImportError:
        console.print("[red]Kill switch module not available.[/red]")


@cli.command(name="preflight")
def preflight():
    """
    Run preflight health checks.

    Validates system readiness before trading.
    """
    console.print("[bold]Preflight Health Checks[/bold]\n")

    try:
        from probablyprofit.utils.preflight import run_preflight_checks_sync

        report = run_preflight_checks_sync(dry_run=True)

        # Show results
        for check in report.checks:
            if check.status.value == "pass":
                console.print(f"  [green]\u2713[/green] {check.name}: {check.message}")
            elif check.status.value == "fail":
                console.print(f"  [red]\u2717[/red] {check.name}: {check.message}")
            elif check.status.value == "warn":
                console.print(f"  [yellow]![/yellow] {check.name}: {check.message}")
            else:
                console.print(f"  [dim]-[/dim] {check.name}: {check.message}")

        console.print()

        if report.passed:
            console.print("[green]All checks passed![/green]")
        else:
            console.print("[red]Some checks failed. Fix issues before trading.[/red]")

    except ImportError:
        console.print("[red]Preflight module not available.[/red]")


@cli.command(name="backup-db")
@click.option("--output", "-o", type=click.Path(), help="Output path for backup")
@click.option("--compress", "-c", is_flag=True, help="Compress backup with gzip")
def backup_db(output: Optional[str], compress: bool):
    """
    Create a backup of the trading database.

    Safely backs up the SQLite database (works even while trading).
    WAL mode allows hot backups without stopping the bot.

    Examples:

        probablyprofit backup-db                     # Auto-named backup
        probablyprofit backup-db -o backup.db       # Custom filename
        probablyprofit backup-db --compress         # Create .gz backup

    For automated backups, add to crontab:

        0 * * * * cd /path/to/bot && probablyprofit backup-db --compress
    """
    import shutil
    import time
    from datetime import datetime

    console.print("[bold]Database Backup[/bold]\n")

    # Find database file
    db_path = os.getenv("DATABASE_PATH", "data/probablyprofit.db")

    # Handle relative paths
    if not os.path.isabs(db_path):
        # Check common locations
        candidates = [
            db_path,
            f"probablyprofit/{db_path}",
            os.path.expanduser(f"~/.probablyprofit/{os.path.basename(db_path)}"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                db_path = candidate
                break

    if not os.path.exists(db_path):
        console.print(f"[red]Database not found: {db_path}[/red]")
        console.print("[dim]Make sure the bot has been run at least once.[/dim]")
        return

    # Generate output path if not specified
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path.home() / ".probablyprofit" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        output = str(backup_dir / f"probablyprofit_backup_{timestamp}.db")

    if compress:
        output = output + ".gz"

    console.print(f"  Source: {db_path}")
    console.print(f"  Output: {output}\n")

    try:
        with console.status("[bold]Creating backup...[/bold]"):
            # For SQLite in WAL mode, we need to checkpoint first for consistency
            # But we can also just copy the files which is safe in WAL mode

            if compress:
                import gzip

                with open(db_path, "rb") as f_in:
                    with gzip.open(output, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(db_path, output)

            # Also backup WAL file if exists
            wal_path = db_path + "-wal"
            shm_path = db_path + "-shm"

            if os.path.exists(wal_path) and not compress:
                shutil.copy2(wal_path, output + "-wal")
            if os.path.exists(shm_path) and not compress:
                shutil.copy2(shm_path, output + "-shm")

        # Get backup size
        backup_size = os.path.getsize(output)
        original_size = os.path.getsize(db_path)

        console.print("[green]Backup created successfully![/green]\n")
        console.print(f"  Original: {original_size / 1024:.1f} KB")
        console.print(f"  Backup:   {backup_size / 1024:.1f} KB")

        if compress:
            ratio = (1 - backup_size / original_size) * 100
            console.print(f"  Compression: {ratio:.1f}% reduction")

        console.print(f"\n  Location: [cyan]{output}[/cyan]")

    except Exception as e:
        console.print(f"[red]Backup failed: {e}[/red]")


@cli.command(name="restore-db")
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, help="Force restore without confirmation")
def restore_db(backup_file: str, force: bool):
    """
    Restore database from a backup.

    WARNING: This will overwrite the current database!

    Example:

        probablyprofit restore-db backup.db
        probablyprofit restore-db backup.db.gz --force
    """
    import shutil

    console.print("[bold]Database Restore[/bold]\n")

    # Find current database
    db_path = os.getenv("DATABASE_PATH", "data/probablyprofit.db")

    if not os.path.isabs(db_path):
        candidates = [
            db_path,
            f"probablyprofit/{db_path}",
            os.path.expanduser(f"~/.probablyprofit/{os.path.basename(db_path)}"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                db_path = candidate
                break

    console.print(f"  Backup:  {backup_file}")
    console.print(f"  Target:  {db_path}\n")

    console.print("[yellow]WARNING: This will overwrite the current database![/yellow]\n")

    if not force:
        if not Confirm.ask("Are you sure you want to restore?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        with console.status("[bold]Restoring database...[/bold]"):
            # Handle compressed backups
            if backup_file.endswith(".gz"):
                import gzip

                with gzip.open(backup_file, "rb") as f_in:
                    with open(db_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(backup_file, db_path)

                # Also restore WAL files if present
                wal_backup = backup_file + "-wal"
                shm_backup = backup_file + "-shm"

                if os.path.exists(wal_backup):
                    shutil.copy2(wal_backup, db_path + "-wal")
                if os.path.exists(shm_backup):
                    shutil.copy2(shm_backup, db_path + "-shm")

        console.print("[green]Database restored successfully![/green]")

    except Exception as e:
        console.print(f"[red]Restore failed: {e}[/red]")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
