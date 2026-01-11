// =========================================================
// ProbablyProfit Website - Interactive Terminal & Utilities
// =========================================================

// Terminal simulation data
const terminalScript = [
    { type: 'command', text: 'probablyprofit run -s strategy.txt --kelly', delay: 50 },
    { type: 'empty', delay: 300 },
    { type: 'line', html: '<span class="success">●</span> Agent: anthropic (claude-sonnet)', delay: 100 },
    { type: 'line', html: '<span class="success">●</span> Strategy loaded from strategy.txt', delay: 80 },
    { type: 'line', html: '<span class="success">●</span> Kelly criterion sizing enabled', delay: 80 },
    { type: 'line', html: '<span class="success">●</span> Risk limits: $100 max position, 5 max open', delay: 80 },
    { type: 'empty', delay: 200 },
    { type: 'line', text: 'Connecting to Polymarket...', class: 'dim', delay: 400 },
    { type: 'line', html: '<span class="success">✓</span> Connected! Found 847 active markets', delay: 100 },
    { type: 'empty', delay: 300 },
    { type: 'line', text: 'Filtering markets by strategy criteria...', class: 'dim', delay: 300 },
    { type: 'line', html: '<span class="success">●</span> 23 markets match your criteria', delay: 100 },
    { type: 'empty', delay: 200 },
    { type: 'line', html: '<span class="notify">◆</span> Analyzing markets with Claude...', delay: 800 },
    { type: 'empty', delay: 300 },
    { type: 'line', html: '<span class="info">Decision:</span> BUY', delay: 100 },
    { type: 'line', html: '  Market: <span class="highlight">Will Bitcoin hit $150k in 2025?</span>', delay: 80 },
    { type: 'line', text: '  Outcome: Yes @ $0.12', delay: 60 },
    { type: 'line', text: '  Size: $15.00 (Kelly: 18% edge)', delay: 60 },
    { type: 'line', text: '  Confidence: 78%', delay: 60 },
    { type: 'line', text: '  Reasoning: "Market undervalues BTC momentum..."', class: 'dim', delay: 60 },
    { type: 'empty', delay: 400 },
    { type: 'line', html: '<span class="success">✓</span> Order placed! Tx: 0x7f3a...c821', delay: 100 },
    { type: 'empty', delay: 600 },
    { type: 'line', html: '<span class="notify">◆</span> Scanning for more opportunities...', delay: 500 },
    { type: 'empty', delay: 300 },
    { type: 'line', html: '<span class="info">Decision:</span> BUY', delay: 100 },
    { type: 'line', html: '  Market: <span class="highlight">Fed rate cut by March 2025?</span>', delay: 80 },
    { type: 'line', text: '  Outcome: No @ $0.35', delay: 60 },
    { type: 'line', text: '  Size: $12.00 (Kelly: 14% edge)', delay: 60 },
    { type: 'line', text: '  Confidence: 71%', delay: 60 },
    { type: 'empty', delay: 400 },
    { type: 'line', html: '<span class="success">✓</span> Order placed! Tx: 0x2e8b...a917', delay: 100 },
    { type: 'empty', delay: 500 },
    { type: 'line', html: '<span class="success">●</span> Portfolio: 2 positions | $27 deployed | $973 available', delay: 100 },
    { type: 'line', text: 'Watching for next opportunity...', class: 'dim', cursor: true, delay: 0 },
];

// Terminal state
let terminalState = {
    running: false,
    currentStep: 0,
    timeouts: [],
};

// Get terminal elements
function getTerminalElements() {
    return {
        content: document.getElementById('terminalContent'),
        status: document.getElementById('terminalStatus'),
        title: document.getElementById('terminalTitle'),
        runBtn: document.querySelector('.term-btn.run'),
        resetBtn: document.querySelector('.term-btn.reset'),
    };
}

// Clear terminal
function clearTerminal() {
    const { content } = getTerminalElements();
    content.innerHTML = '<div class="term-line"><span class="prompt">$</span> <span class="typing-cursor">_</span></div>';
}

// Add line to terminal
function addTerminalLine(config) {
    const { content } = getTerminalElements();
    const line = document.createElement('div');
    line.className = 'term-line';

    if (config.class) {
        line.classList.add(config.class);
    }

    if (config.type === 'empty') {
        line.classList.add('output');
    } else if (config.html) {
        line.innerHTML = config.html;
    } else if (config.text) {
        line.textContent = config.text;
    }

    if (config.cursor) {
        line.innerHTML += '<span class="cursor"></span>';
    }

    content.appendChild(line);
    content.scrollTop = content.scrollHeight;
}

// Type command character by character
async function typeCommand(command, element) {
    return new Promise((resolve) => {
        let i = 0;
        element.innerHTML = '<span class="prompt">$</span> ';

        const interval = setInterval(() => {
            if (i < command.length) {
                element.innerHTML += command[i];
                i++;
            } else {
                clearInterval(interval);
                resolve();
            }
        }, 30);

        terminalState.timeouts.push(interval);
    });
}

// Sleep helper
function sleep(ms) {
    return new Promise(resolve => {
        const timeout = setTimeout(resolve, ms);
        terminalState.timeouts.push(timeout);
    });
}

// Run terminal simulation
async function runTerminal() {
    const els = getTerminalElements();

    if (terminalState.running) return;

    terminalState.running = true;
    terminalState.currentStep = 0;

    // Update UI
    els.status.classList.add('running');
    els.title.textContent = 'terminal — running';
    els.runBtn.disabled = true;

    // Clear and start
    els.content.innerHTML = '';

    for (let i = 0; i < terminalScript.length; i++) {
        if (!terminalState.running) break;

        const step = terminalScript[i];
        terminalState.currentStep = i;

        if (step.type === 'command') {
            // Create command line and type it out
            const cmdLine = document.createElement('div');
            cmdLine.className = 'term-line';
            els.content.appendChild(cmdLine);

            await typeCommand(step.text, cmdLine);
            await sleep(step.delay || 100);
        } else {
            addTerminalLine(step);
            await sleep(step.delay || 100);
        }

        els.content.scrollTop = els.content.scrollHeight;
    }

    // Done
    terminalState.running = false;
    els.status.classList.remove('running');
    els.status.classList.add('success');
    els.title.textContent = 'terminal — completed';
    els.runBtn.disabled = false;
}

// Reset terminal
function resetTerminal() {
    const els = getTerminalElements();

    // Clear all timeouts
    terminalState.timeouts.forEach(t => clearTimeout(t));
    terminalState.timeouts = [];
    terminalState.running = false;
    terminalState.currentStep = 0;

    // Reset UI
    els.status.classList.remove('running', 'success');
    els.title.textContent = 'terminal — click ▶ to run';
    els.runBtn.disabled = false;

    // Clear terminal
    clearTerminal();
}

// Copy install command
function copyInstall() {
    const command = 'pip install probablyprofit';
    const hint = document.getElementById('copyHint');

    navigator.clipboard.writeText(command).then(() => {
        hint.textContent = 'copied!';
        hint.classList.add('copied');

        setTimeout(() => {
            hint.textContent = 'click to copy';
            hint.classList.remove('copied');
        }, 2000);
    });
}

// Copy code example
function copyCode() {
    const codeBlock = document.querySelector('.code-block');
    const btn = document.querySelector('.copy-code-btn');

    // Get text content without HTML tags
    const code = codeBlock.textContent;

    navigator.clipboard.writeText(code).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');

        setTimeout(() => {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
        }, 2000);
    });
}

// FAQ toggle
function toggleFaq(item) {
    // Close other open items
    document.querySelectorAll('.faq-item.active').forEach(el => {
        if (el !== item) {
            el.classList.remove('active');
        }
    });

    // Toggle clicked item
    item.classList.toggle('active');
}

// Strategy examples data
const strategies = [
    {
        name: 'value_investor.txt',
        content: `You are a value investor for prediction markets.

GOAL: Find markets where price doesn't reflect true probability.
Look for cognitive biases, recency bias, and overreaction.

BUY when:
- Market price is 15%+ below your estimate
- High volume (>$10k traded)
- Clear resolution criteria

AVOID:
- Markets with ambiguous outcomes
- Prices between 40-60% (too uncertain)
- Markets resolving in >3 months

SIZING: $10-25 per trade, max 5 positions`
    },
    {
        name: 'momentum.txt',
        content: `You are a momentum trader for prediction markets.

GOAL: Identify markets with strong directional movement
and ride the trend until reversal signals appear.

BUY YES when:
- Price increased 10%+ in last 24 hours
- Volume is 2x above average
- No major news suggesting reversal

BUY NO when:
- Price dropped 10%+ in last 24 hours
- Panic selling visible (high volume, rapid drops)

EXIT when:
- Momentum stalls (3+ hours of sideways)
- Counter-trend volume spike

SIZING: $15-30 per trade, max 3 positions`
    },
    {
        name: 'contrarian.txt',
        content: `You are a contrarian trader for prediction markets.

GOAL: Profit when the crowd is wrong. Look for
overreaction, herd mentality, and extreme sentiment.

BUY when:
- Price moved 20%+ on news that doesn't justify it
- Social media sentiment is extreme (>80% one direction)
- Smart money indicators diverge from price

AVOID:
- Going against genuine fundamental changes
- Markets with insider information risk
- Low liquidity markets (can't exit)

RISK: Contrarian trades are higher risk.
Use smaller sizes: $5-15 per trade, max 3 positions`
    },
    {
        name: 'news_trader.txt',
        content: `You are a news-based trader for prediction markets.

GOAL: React quickly to breaking news before the
market fully prices in new information.

MONITOR:
- Twitter/X for breaking news
- Official government sources
- Major news outlets (Reuters, AP, Bloomberg)

TRADE when:
- News directly impacts market outcome
- Current price doesn't reflect the news yet
- You can verify the news is real (not rumor)

SPEED matters: Enter within 5 minutes of news
EXIT: Take profit at 50% of expected move

SIZING: $20-50 per trade (high conviction only)`
    }
];

// Show strategy
function showStrategy(index) {
    const cards = document.querySelectorAll('.strategy-card');
    cards.forEach((card, i) => {
        card.classList.toggle('active', i === index);
    });

    document.getElementById('strategyFilename').textContent = strategies[index].name;
    document.getElementById('strategyContent').textContent = strategies[index].content;
}

// Copy strategy
function copyStrategy() {
    const content = document.getElementById('strategyContent').textContent;
    const btn = document.querySelector('.copy-strategy-btn');

    navigator.clipboard.writeText(content).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => {
            btn.textContent = 'Copy';
        }, 2000);
    });
}

// Fetch GitHub stars
async function fetchGitHubStars() {
    try {
        const response = await fetch('https://api.github.com/repos/randomness11/probablyprofit');
        const data = await response.json();
        const stars = data.stargazers_count;
        if (stars !== undefined) {
            const el = document.getElementById('githubStars');
            el.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="margin-right:4px"><path d="M12 .587l3.668 7.568 8.332 1.151-6.064 5.828 1.48 8.279-7.416-3.967-7.417 3.967 1.481-8.279-6.064-5.828 8.332-1.151z"/></svg>${stars} Stars`;
        }
    } catch (e) {
        // Silently fail, just show "GitHub"
    }
}

// Fetch stars on load
document.addEventListener('DOMContentLoaded', fetchGitHubStars);

// Auto-run terminal after page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(runTerminal, 3000);
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth' });
        }
    });
});

// Add intersection observer for animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const fadeInObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe elements for fade-in animation
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.feature, .stat, .ai-logo').forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        fadeInObserver.observe(el);
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + Enter to run terminal
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const terminal = document.getElementById('terminal');
        if (terminal && isElementInViewport(terminal)) {
            e.preventDefault();
            runTerminal();
        }
    }

    // Escape to reset terminal
    if (e.key === 'Escape' && terminalState.running) {
        resetTerminal();
    }
});

// Helper to check if element is in viewport
function isElementInViewport(el) {
    const rect = el.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

// Console easter egg
console.log(`
╔═══════════════════════════════════════════════════╗
║                                                   ║
║   [±] probablyprofit                              ║
║                                                   ║
║   AI-powered prediction market trading bots       ║
║   in plain English.                              ║
║                                                   ║
║   pip install probablyprofit                     ║
║   https://github.com/randomness11/probablyprofit ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
`);
