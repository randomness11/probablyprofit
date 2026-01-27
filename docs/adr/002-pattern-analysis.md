# ADR 002: Design Pattern Analysis Report

**Date**: 2026-01-27
**Status**: Documented
**Scope**: ProbablyProfit Codebase Pattern Analysis

## Executive Summary

This document provides a comprehensive analysis of design patterns, anti-patterns, naming conventions, and code duplication in the ProbablyProfit codebase. The codebase demonstrates strong architectural patterns overall, with a few areas identified for improvement.

**Key Findings:**
- Well-implemented Strategy and Template Method patterns across AI agents
- Clean Plugin architecture with proper abstractions
- Consistent naming conventions following PEP 8
- Identified 5 large files that could benefit from modular refactoring
- Minimal code duplication due to shared formatters

---

## 1. Design Patterns in Use

### 1.1 Strategy Pattern (Well Implemented)

**Location**: `/probablyprofit/agent/`

The agent framework excellently implements the Strategy pattern, allowing different AI providers to be swapped interchangeably.

```
BaseAgent (Abstract)
    |
    +-- AnthropicAgent (Claude)
    +-- OpenAIAgent (GPT-4)
    +-- GeminiAgent (Gemini)
```

**Evidence** (`/probablyprofit/agent/base.py`):
```python
class BaseAgent(ABC):
    @abstractmethod
    async def decide(self, observation: Observation) -> Decision:
        """Make a trading decision based on observation."""
        pass
```

Each concrete agent implements `decide()` with provider-specific logic while sharing the common observe-decide-act loop.

**Quality Assessment**: Excellent implementation
- Proper use of ABC and @abstractmethod
- Clean separation between interface and implementation
- Easy to add new AI providers

### 1.2 Template Method Pattern (Well Implemented)

**Location**: `/probablyprofit/agent/base.py`

The `run_loop()` method in BaseAgent defines the algorithm skeleton (observe -> decide -> act) while allowing subclasses to override specific steps.

```python
async def run_loop(self) -> None:
    while self.running:
        observation = await self.observe()  # Template step
        decision = await self.decide(observation)  # Abstract - subclasses implement
        success = await self.act(decision)  # Template step
```

**Quality Assessment**: Excellent
- Clear algorithm skeleton
- Proper hook methods for customization
- Error handling built into template

### 1.3 Repository Pattern (Well Implemented)

**Location**: `/probablyprofit/storage/repositories.py`

Clean data access layer with repository classes for each entity type.

```python
class TradeRepository:
    @staticmethod
    async def create(...) -> TradeRecord
    @staticmethod
    async def get_recent(...) -> List[TradeRecord]
    @staticmethod
    async def search_by_question(...) -> List[TradeRecord]
```

**Quality Assessment**: Good
- Clean separation from business logic
- Consistent async interface
- Uses SQLModel/SQLAlchemy properly

### 1.4 Registry Pattern (Well Implemented)

**Location**: `/probablyprofit/plugins/registry.py`

The PluginRegistry implements a classic registry pattern for plugin discovery and management.

```python
class PluginRegistry:
    def register(self, name: str, plugin_type: PluginType, ...)
    def get(self, name: str, plugin_type: PluginType) -> Optional[PluginInfo]
    def create_instance(self, name: str, plugin_type: PluginType, **kwargs) -> Any
```

**Quality Assessment**: Good
- Supports decorator-based registration
- Type-safe plugin categorization
- Security-conscious discovery (requires explicit trust flag)

### 1.5 Circuit Breaker Pattern (Well Implemented)

**Location**: `/probablyprofit/utils/resilience.py`

Production-grade circuit breaker implementation for API resilience.

```python
class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, ...)
    # States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
```

**Quality Assessment**: Excellent
- Proper state machine (closed/open/half-open)
- Configurable thresholds
- Class-level registry for monitoring
- Thread-safe with asyncio locks

### 1.6 Singleton Pattern (Config Management)

**Location**: `/probablyprofit/config.py`

Global configuration singleton with lazy initialization.

```python
_config: Optional[Config] = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config
```

**Quality Assessment**: Good
- Lazy initialization
- Reset capability for testing
- Multi-source configuration loading

### 1.7 Facade Pattern (API Client)

**Location**: `/probablyprofit/api/client.py`

PolymarketClient provides a simplified interface to multiple complex subsystems (CLOB API, Gamma API, HTTP clients).

**Quality Assessment**: Good, but the file is large (1327 lines)

### 1.8 Decorator Pattern (Resilience)

**Location**: `/probablyprofit/utils/resilience.py`

Composable decorators for retry, circuit breaker, and rate limiting.

```python
@retry(max_attempts=3, base_delay=2.0)
@resilient(circuit_breaker="polymarket", rate_limit_calls=10)
async def fetch_markets():
    ...
```

**Quality Assessment**: Excellent
- Composable decorators
- Configurable per-decorator
- Clean separation of concerns

### 1.9 Patterns That Could Be Applied

| Pattern | Where to Apply | Benefit |
|---------|---------------|---------|
| **Factory Method** | Agent creation in `create_fallback_agent()` | Cleaner agent instantiation |
| **Observer** | Position monitoring and alerts | Decouple event producers from consumers |
| **State** | Agent lifecycle (running/stopped/error) | Cleaner state transitions |
| **Command** | Order execution | Undo/redo capability, queuing |
| **Builder** | Complex configuration objects | Fluent API for config |

---

## 2. Anti-Patterns and Code Smells

### 2.1 God Class / Large File Smell (Medium Severity)

Several files exceed 800 lines, indicating they may have too many responsibilities:

| File | Lines | TODO Present | Recommendation |
|------|-------|--------------|----------------|
| `/probablyprofit/api/client.py` | 1327 | Yes | Split into markets.py, orders.py, positions.py, auth.py |
| `/probablyprofit/cli/main.py` | 1344 | Yes | Split into commands/, handlers/ |
| `/probablyprofit/risk/manager.py` | 879 | Yes | Split into sizing.py, alerts.py, persistence.py |
| `/probablyprofit/agent/base.py` | 816 | Yes | Split into memory.py, lifecycle.py |

**Evidence**: TODOs in source files acknowledge this:
```python
# TODO: Large file refactoring (1039 lines) - consider splitting into:
# - api/markets.py - Market fetching, caching, batch operations
# - api/orders.py - Order placement, cancellation, management
```

**Recommendation**: Refactor according to existing TODO suggestions. Each module should have a single responsibility.

### 2.2 Technical Debt Markers (Low Severity)

Found 5 TODO comments indicating acknowledged technical debt:

1. `/probablyprofit/api/client.py:7` - Large file refactoring
2. `/probablyprofit/risk/manager.py:6` - Large file refactoring
3. `/probablyprofit/cli/main.py:14` - Large file refactoring
4. `/probablyprofit/agent/base.py:6` - Module extraction
5. `/probablyprofit/api/websocket.py:7` - Module extraction

**Assessment**: These are well-documented and planned refactoring tasks, not neglected debt.

### 2.3 Exception Handling Inconsistency (Low Severity)

Some methods catch broad `Exception` while others are more specific:

**Good** (specific exceptions):
```python
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Failed to persist observation - missing module: {e}")
except (ValueError, TypeError) as e:
    logger.warning(f"Failed to persist observation - serialization error: {e}")
```

**Less Ideal** (broad exception):
```python
except Exception as e:
    logger.warning(f"Failed to load plugin from {filename}: {e}")
```

**Recommendation**: Prefer specific exception types where possible.

### 2.4 No Major Anti-Patterns Found

The codebase avoids common anti-patterns:
- No circular imports detected
- No inappropriate intimacy between classes
- No feature envy (methods accessing other objects' data excessively)
- No primitive obsession (proper use of dataclasses and models)
- No long parameter lists (configuration objects used)

---

## 3. Naming Conventions Analysis

### 3.1 PEP 8 Compliance (Excellent)

The codebase consistently follows PEP 8 naming conventions.

#### Classes (PascalCase) - Compliant
```python
class BaseAgent(ABC):
class PolymarketClient:
class CircuitBreaker:
class RiskManager:
class TTLCache(Generic[T]):
```

#### Functions/Methods (snake_case) - Compliant
```python
async def decide(self, observation: Observation) -> Decision:
async def get_markets(self, active: bool = True, ...) -> List[Market]:
def calculate_position_size(self, price: float, ...) -> float:
```

#### Constants (SCREAMING_SNAKE_CASE) - Compliant
```python
MAX_STRATEGY_LENGTH = 10000
SUSPICIOUS_PATTERNS = [...]
CONFIG_DIR = Path.home() / ".probablyprofit"
TEST_PRIVATE_KEY = "0x1111..."
```

#### Module Names (snake_case) - Compliant
```
agent/base.py
agent/anthropic_agent.py
utils/resilience.py
storage/repositories.py
```

### 3.2 Naming Consistency Across Modules

| Convention | Consistency | Examples |
|------------|-------------|----------|
| Agent classes | 100% | `AnthropicAgent`, `OpenAIAgent`, `GeminiAgent` |
| Repository classes | 100% | `TradeRepository`, `ObservationRepository` |
| Exception classes | 100% | `APIException`, `ValidationException` |
| Config dataclasses | 100% | `APIConfig`, `RiskConfig`, `AgentConfig` |

### 3.3 Minor Naming Suggestions

| Current | Suggestion | Reason |
|---------|------------|--------|
| `params_avail` | `clob_params_available` | More descriptive |
| `eth_account_avail` | `eth_account_available` | Avoid abbreviations |
| `_daily_loss_warned` | `_daily_loss_warning_sent` | Clearer intent |

---

## 4. Code Duplication Analysis

### 4.1 Eliminated Duplication (Good)

The codebase shows evidence of proactive duplication elimination:

**Shared Formatter** (`/probablyprofit/agent/formatters.py`):
```python
class ObservationFormatter:
    """
    Formats observations for AI agents.

    Consolidates the formatting logic that was duplicated across
    AnthropicAgent, OpenAIAgent, and GeminiAgent.
    """
```

All three AI agents now use this shared formatter:
- `AnthropicAgent._format_observation()` -> Uses `ObservationFormatter.format_full_observation()`
- `OpenAIAgent._format_observation()` -> Uses `ObservationFormatter.format_full_observation()`
- `GeminiAgent._format_observation()` -> Uses `ObservationFormatter.format_concise()`

### 4.2 Remaining Similar Patterns

#### Decision Parsing Logic
The `_parse_decision` / decision creation logic in agents has similar patterns:

**AnthropicAgent** (lines 120-199):
```python
confidence = float(data.get("confidence", 0.5))
try:
    validate_confidence(confidence)
except ValidationException:
    confidence = max(0.0, min(1.0, confidence))
```

**OpenAIAgent** (lines 196-204):
```python
confidence = float(data.get("confidence", 0.5))
try:
    validate_confidence(confidence)
except ValidationException:
    confidence = max(0.0, min(1.0, confidence))
```

**GeminiAgent** (lines 173-181):
```python
confidence = float(data.get("confidence", 0.5))
try:
    validate_confidence(confidence)
except ValidationException:
    confidence = max(0.0, min(1.0, confidence))
```

**Recommendation**: Extract a `DecisionParser` class or utility function:
```python
# Proposed addition to formatters.py
def parse_decision_from_dict(data: dict, observation: Observation) -> Decision:
    """Parse and validate a decision from AI response data."""
    # Centralized parsing and validation logic
```

#### API Retry Error Handling
Similar retry error handling patterns exist across agents:

```python
# Pattern repeated in all three agents
error_str = str(e).lower()
if any(x in error_str for x in ["timeout", "connection", "rate limit", ...]):
    raise NetworkException(f"API transient error: {e}")
raise AgentException(f"API error: {e}")
```

**Recommendation**: Create a shared error classifier function in `utils/resilience.py`.

### 4.3 Duplication Metrics Summary

| Category | Status | Notes |
|----------|--------|-------|
| Observation formatting | Eliminated | Shared `ObservationFormatter` |
| Decision schema | Eliminated | Shared `get_decision_schema()` |
| Strategy validation | Eliminated | Shared in `utils/validators.py` |
| API retry logic | Exists | Similar patterns, could be extracted |
| Decision parsing | Exists | Similar validation patterns |

---

## 5. Architectural Boundary Analysis

### 5.1 Layer Structure (Good)

The codebase follows a clean layered architecture:

```
+------------------+
|    CLI Layer     |  (cli/main.py)
+------------------+
         |
+------------------+
|   Agent Layer    |  (agent/*)
+------------------+
         |
+------------------+
|  Service Layer   |  (risk/, utils/, sources/)
+------------------+
         |
+------------------+
|  Infrastructure  |  (api/, storage/, alerts/)
+------------------+
```

### 5.2 Boundary Compliance

| Boundary | Compliance | Notes |
|----------|------------|-------|
| CLI -> Agent | Good | CLI creates agents, doesn't access internals |
| Agent -> API | Good | Agents use client abstraction |
| Agent -> Storage | Good | Uses repository pattern |
| Utils -> Core | Good | Utils are dependency-free helpers |

### 5.3 Cross-Cutting Concerns

Properly implemented:
- **Logging**: Centralized in `utils/logging.py` with secret redaction
- **Configuration**: Centralized in `config.py` with validation
- **Exceptions**: Hierarchy in `api/exceptions.py`
- **Resilience**: Decorators in `utils/resilience.py`

---

## 6. Recommendations Summary

### High Priority

1. **Split Large Files**: Refactor the 4 files exceeding 800 lines according to existing TODO suggestions
2. **Extract Decision Parsing**: Create shared `DecisionParser` utility to eliminate duplication

### Medium Priority

3. **Standardize Error Classification**: Create shared error classifier for API retry logic
4. **Apply Factory Pattern**: Consider factory method for agent creation
5. **Add Observer Pattern**: For position monitoring and alerting

### Low Priority

6. **Expand Naming Abbreviations**: `params_avail` -> `clob_params_available`
7. **Add Builder Pattern**: For complex configuration object construction

---

## 7. Pattern Implementation Quality Scores

| Pattern | Implementation | Quality Score |
|---------|---------------|---------------|
| Strategy (Agents) | Excellent | 9/10 |
| Template Method | Excellent | 9/10 |
| Repository | Good | 8/10 |
| Registry (Plugins) | Good | 8/10 |
| Circuit Breaker | Excellent | 9/10 |
| Decorator (Resilience) | Excellent | 9/10 |
| Facade (API Client) | Good | 7/10 (large file) |
| Singleton (Config) | Good | 8/10 |

**Overall Architecture Score**: 8.3/10

The codebase demonstrates strong design pattern usage and clean architecture. The main areas for improvement are file size management and minor code duplication in AI agent decision parsing logic.

---

## Appendix: Files Analyzed

```
probablyprofit/
  agent/
    __init__.py
    base.py (816 lines)
    anthropic_agent.py (418 lines)
    openai_agent.py (237 lines)
    gemini_agent.py (214 lines)
    ensemble.py (409 lines)
    fallback.py (414 lines)
    formatters.py (157 lines)
  api/
    client.py (1327 lines)
    exceptions.py (100 lines)
  plugins/
    base.py (159 lines)
    registry.py (211 lines)
  storage/
    database.py (197 lines)
    repositories.py (257 lines)
  utils/
    resilience.py (539 lines)
    cache.py (402 lines)
    validators.py (427 lines)
  risk/
    manager.py (879 lines)
  config.py (850 lines)
```
