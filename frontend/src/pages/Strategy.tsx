import { useState, useRef, useCallback } from 'react';
import Editor, { OnMount, OnChange } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import {
  Save,
  Upload,
  Download,
  Play,
  FileText,
  CheckCircle,
  AlertCircle,
  Trash2,
  Plus,
  Copy,
  Sparkles,
} from 'lucide-react';

// Pre-built strategy templates
const TEMPLATES = [
  {
    name: 'Value Investor',
    filename: 'value_investor.txt',
    content: `You are a value investor for prediction markets.

GOAL: Find markets where price doesn't reflect true probability.
Look for cognitive biases, recency bias, and overreaction.

BUY YES when:
- Market price is 15%+ below your estimated probability
- High volume (>$10k traded)
- Clear resolution criteria
- Time to resolution > 7 days

BUY NO when:
- Market price is 15%+ above your estimated probability
- Same liquidity/clarity requirements

AVOID:
- Markets with ambiguous outcomes
- Prices between 40-60% (too uncertain)
- Markets resolving in >3 months
- Celebrity/meme markets

SIZING:
- Base: $10-25 per trade
- High conviction (25%+ edge): $40-50
- Max 5 concurrent positions

EXIT:
- Take profit at 2x
- Stop loss at -30%
- Close 24h before resolution`,
  },
  {
    name: 'Momentum Trader',
    filename: 'momentum.txt',
    content: `You are a momentum trader for prediction markets.

GOAL: Identify markets with strong directional movement
and ride the trend until reversal signals appear.

BUY YES when:
- Price increased 10%+ in last 24 hours
- Volume is 2x above average
- No major news suggesting reversal
- Trend aligns with fundamentals

BUY NO when:
- Price dropped 10%+ in last 24 hours
- Panic selling visible (high volume, rapid drops)
- Fundamentals support the downtrend

EXIT SIGNALS:
- Momentum stalls (3+ hours of sideways)
- Counter-trend volume spike
- Take profit at +50%
- Stop loss at -20%

SIZING:
- $15-30 per trade
- Max 3 positions
- Scale in on confirmation

AVOID:
- Fighting strong trends
- Low volume markets
- News-driven spikes (wait for confirmation)`,
  },
  {
    name: 'News Trader',
    filename: 'news_trader.txt',
    content: `You are a news-based trader for prediction markets.

GOAL: React quickly to breaking news before the
market fully prices in new information.

MONITOR:
- Twitter/X for breaking news
- Official government sources
- Major news outlets (Reuters, AP, Bloomberg)
- Primary sources when possible

TRADE when:
- News directly impacts market outcome
- Current price doesn't reflect the news yet
- You can verify the news is real (not rumor)
- Impact is significant (>10% probability shift)

SPEED matters:
- Enter within 5 minutes of confirmed news
- Use market orders for speed
- Don't wait for "perfect" entry

EXIT:
- Take profit at 50% of expected move
- If market doesn't move in 30 min, reassess
- Stop loss at -15%

SIZING:
- $20-50 per trade (high conviction only)
- Single position per news event
- Never average down on news trades

AVOID:
- Unverified rumors
- Already priced-in news
- Ambiguous impact news`,
  },
  {
    name: 'Arbitrage Hunter',
    filename: 'arbitrage.txt',
    content: `You are an arbitrage hunter across prediction markets.

GOAL: Find price discrepancies between related markets
within Polymarket.

LOOK FOR:
- Related events with inconsistent prices
- Correlated markets with pricing discrepancies
- YES + NO prices that don't sum to ~1.00
- Time-based arbitrage opportunities

EXECUTE when:
- Combined cost < 0.95 for guaranteed $1 payout
- Spread is > 3% after fees
- Both sides have sufficient liquidity
- Execution risk is manageable

SIZING:
- Equal $ on both sides
- Max $100 per arbitrage
- Account for fees on both platforms

RISK MANAGEMENT:
- Verify markets have same resolution criteria
- Check for timing differences in resolution
- Monitor for market manipulation
- Have exit plan if one side moves against you

AVOID:
- Markets with different resolution dates
- Ambiguous or subjective outcomes
- Low liquidity on either side
- Cross-platform execution risk > 2%`,
  },
  {
    name: 'Contrarian',
    filename: 'contrarian.txt',
    content: `You are a contrarian trader for prediction markets.

GOAL: Profit when the crowd is wrong. Look for
overreaction, herd mentality, and extreme sentiment.

BUY AGAINST THE CROWD when:
- Price moved 20%+ on news that doesn't justify it
- Social media sentiment is extreme (>80% one direction)
- Smart money indicators diverge from retail
- Historical base rates suggest overreaction

CONFIRMATION SIGNALS:
- Volume spike on the move (panic/FOMO)
- Price at extreme levels (>85% or <15%)
- No fundamental change to justify move
- Mean reversion patterns forming

AVOID going contrarian when:
- Genuine fundamental shift occurred
- Insider information risk is high
- Low liquidity (can't exit)
- Trend is backed by new information

SIZING:
- Smaller sizes: $5-15 per trade
- Max 3 contrarian positions
- Scale in slowly

EXIT:
- Take profit when sentiment normalizes
- Stop loss at -25%
- Time-based exit: 7 days max hold`,
  },
];

// Strategy validation rules
interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

function validateStrategy(content: string): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // Check minimum length
  if (content.length < 50) {
    errors.push('Strategy is too short. Add more detail about your trading approach.');
  }

  // Check for key sections
  const hasGoal = /goal|objective|purpose/i.test(content);
  const hasBuyRules = /buy\s+(yes|no|when)/i.test(content);
  const hasAvoid = /avoid|don't|never/i.test(content);
  const hasSizing = /size|sizing|\$\d+|position/i.test(content);
  const hasExit = /exit|stop.?loss|take.?profit|sell/i.test(content);

  if (!hasGoal) {
    warnings.push('Consider adding a GOAL section to clarify your strategy objective.');
  }
  if (!hasBuyRules) {
    errors.push('Missing buy rules. Add conditions for when to BUY YES or BUY NO.');
  }
  if (!hasAvoid) {
    warnings.push('Consider adding an AVOID section to specify what markets to skip.');
  }
  if (!hasSizing) {
    warnings.push('No position sizing rules found. Add $ amounts or sizing guidelines.');
  }
  if (!hasExit) {
    warnings.push('No exit rules found. Add stop-loss and take-profit conditions.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

export function Strategy() {
  const [strategies, setStrategies] = useState<{ name: string; content: string }[]>([
    { name: 'my_strategy.txt', content: TEMPLATES[0].content },
  ]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [validation, setValidation] = useState<ValidationResult>(() =>
    validateStrategy(TEMPLATES[0].content)
  );
  const [saved, setSaved] = useState(true);
  const [showTemplates, setShowTemplates] = useState(false);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const activeStrategy = strategies[activeIndex];

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Register custom language for strategy files
    monaco.languages.register({ id: 'strategy' });

    // Define syntax highlighting
    monaco.languages.setMonarchTokensProvider('strategy', {
      tokenizer: {
        root: [
          // Section headers
          [/^(GOAL|OBJECTIVE|PURPOSE|BUY|SELL|AVOID|SIZING|EXIT|RISK|MONITOR|LOOK FOR|EXECUTE|CONFIRMATION|EDGE):/i, 'keyword'],
          // Conditions
          [/\b(when|if|unless|and|or|but)\b/i, 'keyword.control'],
          // Numbers and percentages
          [/\b\d+(\.\d+)?%?\b/, 'number'],
          // Currency
          [/\$\d+(\.\d+)?/, 'number.currency'],
          // YES/NO outcomes
          [/\b(YES|NO)\b/, 'type'],
          // Important words
          [/\b(max|min|never|always|must|should)\b/i, 'keyword.important'],
          // Bullet points
          [/^[\s]*[-•]/, 'comment'],
          // Comments
          [/#.*$/, 'comment'],
        ],
      },
    });

    // Define theme colors
    monaco.editor.defineTheme('strategy-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'keyword', foreground: 'c084fc', fontStyle: 'bold' },
        { token: 'keyword.control', foreground: '60a5fa' },
        { token: 'keyword.important', foreground: 'f472b6', fontStyle: 'bold' },
        { token: 'number', foreground: '4ade80' },
        { token: 'number.currency', foreground: '22c55e', fontStyle: 'bold' },
        { token: 'type', foreground: 'fbbf24', fontStyle: 'bold' },
        { token: 'comment', foreground: '64748b' },
      ],
      colors: {
        'editor.background': '#0a0a0b',
        'editor.foreground': '#e2e8f0',
        'editor.lineHighlightBackground': '#1e1e1e',
        'editor.selectionBackground': '#8b5cf644',
        'editorCursor.foreground': '#8b5cf6',
        'editorLineNumber.foreground': '#475569',
        'editorLineNumber.activeForeground': '#94a3b8',
      },
    });

    monaco.editor.setTheme('strategy-dark');
  };

  const handleEditorChange: OnChange = (value) => {
    if (value !== undefined) {
      const updated = [...strategies];
      updated[activeIndex] = { ...updated[activeIndex], content: value };
      setStrategies(updated);
      setValidation(validateStrategy(value));
      setSaved(false);
    }
  };

  const handleSave = useCallback(() => {
    // In a real app, this would save to backend
    setSaved(true);
    // Could also save to localStorage
    localStorage.setItem('strategies', JSON.stringify(strategies));
  }, [strategies]);

  const handleDownload = () => {
    const blob = new Blob([activeStrategy.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = activeStrategy.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const content = e.target?.result as string;
          setStrategies([...strategies, { name: file.name, content }]);
          setActiveIndex(strategies.length);
          setValidation(validateStrategy(content));
          setSaved(false);
        };
        reader.readAsText(file);
      }
    };
    input.click();
  };

  const handleNewStrategy = () => {
    const name = `strategy_${strategies.length + 1}.txt`;
    setStrategies([...strategies, { name, content: '' }]);
    setActiveIndex(strategies.length);
    setValidation(validateStrategy(''));
    setSaved(false);
  };

  const handleDeleteStrategy = (index: number) => {
    if (strategies.length === 1) return;
    const updated = strategies.filter((_, i) => i !== index);
    setStrategies(updated);
    if (activeIndex >= updated.length) {
      setActiveIndex(updated.length - 1);
    }
    setSaved(false);
  };

  const handleLoadTemplate = (template: typeof TEMPLATES[0]) => {
    setStrategies([...strategies, { name: template.filename, content: template.content }]);
    setActiveIndex(strategies.length);
    setValidation(validateStrategy(template.content));
    setShowTemplates(false);
    setSaved(false);
  };

  const handleCopyStrategy = () => {
    navigator.clipboard.writeText(activeStrategy.content);
  };

  const handleRename = (index: number, newName: string) => {
    const updated = [...strategies];
    updated[index] = { ...updated[index], name: newName };
    setStrategies(updated);
    setSaved(false);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[calc(100vh-200px)]">
      {/* Sidebar */}
      <div className="lg:col-span-1 flex flex-col gap-4">
        {/* Strategy Files */}
        <div className="glass rounded-xl p-4 flex-1">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Strategies</h2>
            <button
              onClick={handleNewStrategy}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
              title="New Strategy"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-1">
            {strategies.map((strategy, index) => (
              <div
                key={index}
                className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                  index === activeIndex
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white'
                }`}
                onClick={() => {
                  setActiveIndex(index);
                  setValidation(validateStrategy(strategy.content));
                }}
              >
                <FileText className="w-4 h-4 flex-shrink-0" />
                <input
                  type="text"
                  value={strategy.name}
                  onChange={(e) => handleRename(index, e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 bg-transparent text-sm truncate focus:outline-none focus:bg-white/5 rounded px-1"
                />
                {strategies.length > 1 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteStrategy(index);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Templates */}
        <div className="glass rounded-xl p-4">
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            className="flex items-center gap-2 w-full text-left"
          >
            <Sparkles className="w-4 h-4 text-yellow-400" />
            <span className="font-semibold">Templates</span>
          </button>
          {showTemplates && (
            <div className="mt-3 space-y-1">
              {TEMPLATES.map((template, index) => (
                <button
                  key={index}
                  onClick={() => handleLoadTemplate(template)}
                  className="w-full text-left px-3 py-2 text-sm text-slate-400 hover:bg-white/5 hover:text-white rounded-lg transition-colors"
                >
                  {template.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Validation */}
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            {validation.valid ? (
              <CheckCircle className="w-4 h-4 text-green-400" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-400" />
            )}
            <span className="font-semibold text-sm">
              {validation.valid ? 'Valid Strategy' : 'Issues Found'}
            </span>
          </div>
          {validation.errors.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-red-400 font-medium mb-1">Errors</p>
              <ul className="space-y-1">
                {validation.errors.map((error, i) => (
                  <li key={i} className="text-xs text-slate-400 flex items-start gap-1">
                    <span className="text-red-400 mt-0.5">•</span>
                    {error}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {validation.warnings.length > 0 && (
            <div>
              <p className="text-xs text-yellow-400 font-medium mb-1">Suggestions</p>
              <ul className="space-y-1">
                {validation.warnings.map((warning, i) => (
                  <li key={i} className="text-xs text-slate-400 flex items-start gap-1">
                    <span className="text-yellow-400 mt-0.5">•</span>
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="lg:col-span-3 flex flex-col">
        {/* Toolbar */}
        <div className="glass rounded-t-xl p-3 flex items-center justify-between border-b border-white/5">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-400">Editing:</span>
            <span className="text-sm font-mono text-white">{activeStrategy.name}</span>
            {!saved && (
              <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded">
                Unsaved
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyStrategy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
              title="Copy to clipboard"
            >
              <Copy className="w-4 h-4" />
            </button>
            <button
              onClick={handleUpload}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
              title="Upload strategy file"
            >
              <Upload className="w-4 h-4" />
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
              title="Download strategy"
            >
              <Download className="w-4 h-4" />
            </button>
            <div className="w-px h-6 bg-white/10" />
            <button
              onClick={handleSave}
              disabled={saved}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                saved
                  ? 'text-slate-500 cursor-not-allowed'
                  : 'text-green-400 hover:bg-green-400/10'
              }`}
            >
              <Save className="w-4 h-4" />
              Save
            </button>
            <button
              className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-purple-500 hover:bg-purple-600 text-white rounded-lg transition-colors"
              title="Run with this strategy"
            >
              <Play className="w-4 h-4" />
              Run
            </button>
          </div>
        </div>

        {/* Monaco Editor */}
        <div className="flex-1 glass rounded-b-xl overflow-hidden">
          <Editor
            height="100%"
            defaultLanguage="strategy"
            value={activeStrategy.content}
            onChange={handleEditorChange}
            onMount={handleEditorMount}
            options={{
              fontSize: 14,
              fontFamily: "'JetBrains Mono', monospace",
              lineHeight: 1.6,
              padding: { top: 16, bottom: 16 },
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              lineNumbers: 'on',
              renderLineHighlight: 'line',
              cursorBlinking: 'smooth',
              cursorSmoothCaretAnimation: 'on',
              smoothScrolling: true,
              bracketPairColorization: { enabled: false },
              guides: { indentation: false },
            }}
            loading={
              <div className="flex items-center justify-center h-full text-slate-400">
                Loading editor...
              </div>
            }
          />
        </div>
      </div>
    </div>
  );
}
