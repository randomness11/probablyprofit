# ADR-001: Architecture Review - ProbablyProfit Codebase

**Status:** Accepted
**Date:** 2026-01-27
**Author:** Architecture Review

## Executive Summary

This Architecture Decision Record documents a comprehensive review of the ProbablyProfit codebase, focusing on async consistency, module boundaries, plugin security, and error recovery patterns. The codebase demonstrates strong architectural foundations with well-designed patterns, though several areas require attention for production hardening.

---

## 1. Async Consistency

### 1.1 Overall Assessment

The codebase demonstrates **good async consistency** with proper use of `async/await` patterns throughout. The core agent loop (`observe -> decide -> act`) is fully asynchronous and correctly handles concurrency.

### 1.2 Positive Patterns Identified

**Proper Async Context Manager Usage:**

```python
# /probablyprofit/storage/database.py:161-171
@asynccontextmanager
async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
    async with self.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
```

**Thread-Safe State Management:**

```python
# /probablyprofit/agent/base.py:83-91
# AgentMemory uses asyncio.Lock for thread-safe operations
self._lock = asyncio.Lock()

async def add_observation(self, observation: Observation) -> None:
    async with self._lock:
        self.observations.append(observation)
```

**Graceful Shutdown Handling:**

```python
# /probablyprofit/agent/base.py:711-719
# Uses asyncio.Event for clean shutdown signaling
try:
    await asyncio.wait_for(self._stop_event.wait(), timeout=self.loop_interval)
    break  # Stop requested
except asyncio.TimeoutError:
    pass  # Normal timeout, continue loop
```

### 1.3 Issues Found

#### Issue 1: Synchronous SDK Calls Wrapped Inconsistently

**Location:** `/probablyprofit/agent/anthropic_agent.py:227-235`

The Anthropic agent correctly uses `asyncio.to_thread()` for sync SDK calls:

```python
response = await asyncio.to_thread(
    self.anthropic.messages.create,
    model=self.model,
    ...
)
```

However, the streaming method `decide_streaming()` at line 331 is **synchronous**, which could block the event loop:

```python
# /probablyprofit/agent/anthropic_agent.py:385-394
with self.anthropic.messages.stream(...) as stream:
    for text in stream.text_stream:
        full_response += text
```

**Recommendation:** Convert `decide_streaming()` to async or document it as CLI-only (not for use in async contexts).

#### Issue 2: Rate Limiter Lock Initialization

**Location:** `/probablyprofit/risk/manager.py:104-114`

The async lock is lazily initialized, which could cause issues if accessed before event loop:

```python
def _get_async_lock(self) -> asyncio.Lock:
    if self._async_lock is None:
        self._async_lock = asyncio.Lock()
    return self._async_lock
```

**Recommendation:** Document that RiskManager must be used within an async context or move lock creation to async init.

#### Issue 3: Deprecated `asyncio.get_event_loop()` Usage

**Location:** `/probablyprofit/api/client.py:1219-1224`

```python
loop = asyncio.get_event_loop()
balance = await asyncio.wait_for(
    loop.run_in_executor(None, self.client.get_balance), timeout=5.0
)
```

**Recommendation:** Use `asyncio.to_thread()` (Python 3.9+) for consistency:

```python
balance = await asyncio.wait_for(
    asyncio.to_thread(self.client.get_balance), timeout=5.0
)
```

### 1.4 Async Patterns Consistency Across Agents

All three AI agent implementations (Anthropic, OpenAI, Gemini) use consistent patterns:

| Component | AnthropicAgent | OpenAIAgent | GeminiAgent |
|-----------|---------------|-------------|-------------|
| SDK Call Wrapper | `asyncio.to_thread()` | `asyncio.to_thread()` | `asyncio.to_thread()` |
| Retry Decorator | `@retry()` | `@retry()` | `@retry()` |
| Rate Limiting | `AIRateLimiter` | Not implemented | Not implemented |
| Error Handling | `AgentException`, `NetworkException` | Same | Same |

**Recommendation:** Add `AIRateLimiter` to OpenAI and Gemini agents for consistency.

---

## 2. Module Boundaries

### 2.1 Current Architecture

```
probablyprofit/
    api/          # Platform integration (Polymarket)
    agent/        # AI decision-making agents
    risk/         # Risk management primitives
    storage/      # Data persistence layer
    plugins/      # Extensibility framework
    trading/      # Order execution
    utils/        # Cross-cutting utilities
    alerts/       # Notification systems
```

### 2.2 Dependency Analysis

#### Clean Layering Assessment

| Layer | Depends On | Proper Layering? |
|-------|-----------|-----------------|
| `agent/` | `api/`, `risk/`, `storage/`, `alerts/`, `utils/` | Yes |
| `api/` | `utils/`, `config` | Yes |
| `risk/` | `alerts/`, `storage/`, `config` | Mostly |
| `storage/` | None (standalone) | Yes |
| `plugins/` | None (standalone) | Yes |

**Positive Finding:** No circular dependencies detected. Lazy imports are used in `/probablyprofit/api/__init__.py` to prevent import cycles.

### 2.3 Module Coupling Analysis

#### High Cohesion Examples

**Storage Module:** Properly separated concerns:
- `database.py` - Connection management
- `models.py` - Data models (SQLModel)
- `repositories.py` - Data access patterns
- `historical.py` - Historical data operations

**Risk Module:** Clean separation:
- `manager.py` - Core risk calculations
- `positions.py` - Position tracking, correlation detection

#### Areas Requiring Attention

**Issue 1: Large File Complexity**

The codebase contains several files flagged for refactoring:

| File | Lines | Recommendation |
|------|-------|---------------|
| `/probablyprofit/api/client.py` | ~1328 | Split into `markets.py`, `orders.py`, `positions.py`, `auth.py` |
| `/probablyprofit/risk/manager.py` | ~880 | Split into `sizing.py`, `alerts.py`, `persistence.py`, `limits.py` |
| `/probablyprofit/agent/base.py` | ~817 | Extract `memory.py`, `lifecycle.py`, `execution.py` |
| `/probablyprofit/api/websocket.py` | ~634 | Extract `connection.py`, `subscriptions.py`, `handlers.py` |

**Issue 2: Config Module Cross-Cutting**

`config.py` is imported by nearly every module. This is acceptable for configuration but creates tight coupling.

**Recommendation:** Consider a dependency injection pattern for testing flexibility.

**Issue 3: Direct Storage Access from Agent**

The `BaseAgent` directly imports from `storage/`:

```python
# /probablyprofit/agent/base.py:128-131
from probablyprofit.storage.repositories import ObservationRepository
async with self._db_manager.get_session() as session:
    await ObservationRepository.create(...)
```

**Recommendation:** Introduce a service layer or use dependency injection:

```python
# Preferred pattern
class AgentPersistenceService:
    async def save_observation(self, observation: Observation) -> None:
        ...
```

### 2.4 Proper Abstraction Levels

**Well-Designed Abstractions:**

1. **BaseAgent Abstract Class** - Clean template method pattern for observe/decide/act
2. **Plugin Base Classes** - Proper interface segregation (DataSourcePlugin, AgentPlugin, etc.)
3. **Exception Hierarchy** - Clear hierarchy from `Poly16zException` down

**Abstraction Concerns:**

The `PolymarketClient` handles both HTTP and CLOB operations. Consider separating:
- `GammaAPIClient` - Market metadata
- `CLOBClient` - Order operations
- `PolymarketClient` - Facade combining both

---

## 3. Plugin Security Architecture

### 3.1 Current Security Model

**Location:** `/probablyprofit/plugins/registry.py`

The plugin system includes explicit security warnings and requires trust acknowledgment:

```python
def discover_plugins(self, path: str, trusted: bool = False) -> int:
    if not trusted:
        raise SecurityError(
            "Plugin discovery requires explicit trust acknowledgment."
        )
```

### 3.2 Security Risks

| Risk | Current Mitigation | Severity |
|------|-------------------|----------|
| Arbitrary code execution | `trusted=True` requirement | High |
| Credential theft | Warning in docstring | High |
| System command execution | None | High |
| Trading behavior modification | None | Medium |
| Data exfiltration | None | Medium |

### 3.3 Recommended Sandboxing Approaches

#### Option A: Process Isolation (Recommended for Production)

```python
import multiprocessing
from multiprocessing import Process, Queue

class SandboxedPluginRunner:
    """Run plugins in isolated processes with limited capabilities."""

    def __init__(self, plugin_path: str):
        self.plugin_path = plugin_path
        self.result_queue = Queue()

    def run_isolated(self, method: str, *args, timeout: float = 30.0):
        """Execute plugin method in isolated process."""
        process = Process(
            target=self._run_in_sandbox,
            args=(method, args, self.result_queue)
        )
        process.start()
        process.join(timeout=timeout)

        if process.is_alive():
            process.terminate()
            raise TimeoutError("Plugin execution timed out")

        return self.result_queue.get_nowait()
```

#### Option B: Restricted Execution Environment

```python
import RestrictedPython
from RestrictedPython import compile_restricted

class RestrictedPluginLoader:
    """Load plugins with restricted Python execution."""

    ALLOWED_IMPORTS = frozenset(['math', 'datetime', 'json'])

    def load_plugin(self, code: str):
        byte_code = compile_restricted(
            code,
            filename='<plugin>',
            mode='exec'
        )

        restricted_globals = {
            '__builtins__': self._get_safe_builtins(),
            '__import__': self._restricted_import,
        }

        exec(byte_code, restricted_globals)
        return restricted_globals
```

#### Option C: Capability-Based Security

```python
from dataclasses import dataclass
from typing import Set

@dataclass
class PluginCapabilities:
    """Declarative capabilities for plugins."""
    can_read_markets: bool = True
    can_place_orders: bool = False
    can_access_network: bool = False
    can_access_filesystem: bool = False
    allowed_api_endpoints: Set[str] = frozenset()

class CapabilityEnforcedPlugin(BasePlugin):
    """Plugin wrapper that enforces declared capabilities."""

    required_capabilities: PluginCapabilities

    def __init__(self, wrapped_plugin: BasePlugin, granted: PluginCapabilities):
        self._wrapped = wrapped_plugin
        self._granted = granted
        self._validate_capabilities()
```

### 3.4 Recommended Security Boundaries

```
+------------------+     +-------------------+     +------------------+
|  Trusted Core    |     |  Plugin Sandbox   |     |  External APIs   |
|                  |     |                   |     |                  |
|  - Agent Loop    |<--->|  - Data Plugins   |<--->|  - AI Providers  |
|  - Risk Manager  |     |  - Strategy Logic |     |  - Polymarket    |
|  - Order Manager |     |  - Custom Signals |     |                  |
+------------------+     +-------------------+     +------------------+
        |                        |
        v                        v
+--------------------------------------------------+
|              Audit Log / Monitoring              |
+--------------------------------------------------+
```

### 3.5 Implementation Recommendations

1. **Plugin Manifest:** Require `plugin.yaml` declaring capabilities and permissions
2. **Code Signing:** Implement cryptographic signatures for verified plugins
3. **Resource Limits:** Add CPU/memory limits via `resource` module
4. **Network Isolation:** Use network namespaces for plugins requiring internet
5. **Audit Logging:** Log all plugin actions for security review

---

## 4. Error Recovery Patterns

### 4.1 Current Implementation

**Location:** `/probablyprofit/utils/resilience.py`

The codebase implements comprehensive error recovery patterns:

#### Retry with Exponential Backoff

```python
# /probablyprofit/utils/resilience.py:79-165
@retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    retryable_exceptions=(NetworkException, RateLimitException, ...),
)
async def fetch_markets():
    ...
```

**Features:**
- Configurable retry attempts and delays
- Exponential backoff with jitter (prevents thundering herd)
- Retryable vs non-retryable exception classification

#### Circuit Breaker Pattern

```python
# /probablyprofit/utils/resilience.py:200-336
class CircuitBreaker:
    """States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED"""

    def __init__(self, name: str, failure_threshold: int = 5, timeout: float = 30.0):
        ...
```

**Features:**
- Three-state machine (CLOSED, OPEN, HALF_OPEN)
- Configurable failure threshold and recovery timeout
- Global registry for circuit breaker status monitoring

### 4.2 Transient vs Permanent Error Classification

**Location:** `/probablyprofit/api/exceptions.py`

```
Poly16zException (Base)
    |
    +-- APIException
    |       |
    |       +-- NetworkException (Transient - Retry)
    |       +-- RateLimitException (Transient - Retry with backoff)
    |       +-- AuthenticationException (Permanent - Fail fast)
    |
    +-- ValidationException (Permanent - Fail fast)
    +-- OrderException (Mixed - Context dependent)
    +-- RiskLimitException (Permanent - Fail fast)
```

**Proper Classification in Code:**

```python
# /probablyprofit/agent/anthropic_agent.py:246-256
except (ConnectionError, TimeoutError) as e:
    raise NetworkException(f"Claude API connection error: {e}")  # Transient
except Exception as e:
    error_str = str(e).lower()
    if any(x in error_str for x in ["timeout", "rate limit", "529", "503"]):
        raise NetworkException(f"Transient error: {e}")  # Transient
    raise AgentException(f"Claude API error: {e}")  # Permanent
```

### 4.3 Issues Found

#### Issue 1: Inconsistent Retry Configuration

Different modules use different retry configurations:

| Module | Max Attempts | Base Delay | Max Delay |
|--------|-------------|------------|-----------|
| `anthropic_agent.py` | 3 | 2.0s | 30.0s |
| `openai_agent.py` | 3 | 2.0s | 30.0s |
| `gemini_agent.py` | 3 | 2.0s | 30.0s |
| `client.py` | Config-based | Config-based | Config-based |

**Recommendation:** Centralize retry configuration in `config.py`:

```python
class RetryConfig:
    ai_api_max_attempts: int = 3
    ai_api_base_delay: float = 2.0
    ai_api_max_delay: float = 30.0

    market_api_max_attempts: int = 5
    market_api_base_delay: float = 1.0
    market_api_max_delay: float = 60.0
```

#### Issue 2: Missing Circuit Breaker on AI APIs

The Polymarket API has circuit breakers configured:

```python
# /probablyprofit/api/client.py:67-81
"gamma": CircuitBreaker("polymarket-gamma", ...),
"clob": CircuitBreaker("polymarket-clob", ...),
```

However, AI provider APIs lack circuit breakers. A cascading failure in Claude API would not trip any circuit.

**Recommendation:** Add circuit breakers for AI providers:

```python
# In agent/__init__.py or config.py
AI_CIRCUIT_BREAKERS = {
    "anthropic": CircuitBreaker("anthropic-api", failure_threshold=3),
    "openai": CircuitBreaker("openai-api", failure_threshold=3),
    "gemini": CircuitBreaker("gemini-api", failure_threshold=3),
}
```

#### Issue 3: Partial Fill Timeout Handling

**Location:** `/probablyprofit/api/order_manager.py:439-488`

The `check_partial_fill_timeouts()` method handles stale partial fills well, but timeout is hardcoded to 300s (5 minutes).

**Recommendation:** Make configurable and add alerting:

```python
def __init__(self, ..., partial_fill_timeout: Optional[float] = None):
    self.partial_fill_timeout = partial_fill_timeout or get_config().trading.partial_fill_timeout
```

### 4.4 Recovery Pattern Summary

| Pattern | Implementation Status | Location |
|---------|----------------------|----------|
| Retry with Backoff | Implemented | `/utils/resilience.py` |
| Circuit Breaker | Partial (API only) | `/utils/resilience.py`, `/api/client.py` |
| Rate Limiting | Implemented | `/utils/resilience.py`, `/utils/ai_rate_limiter.py` |
| Graceful Degradation | Implemented | Ensemble fallback, cache fallback |
| Checkpoint/Recovery | Implemented | `/utils/recovery.py`, `/risk/manager.py` |
| Kill Switch | Implemented | `/utils/killswitch.py` |
| Max Drawdown Protection | Implemented | `/risk/manager.py` |

---

## 5. Summary of Recommendations

### High Priority

1. **Add Circuit Breakers to AI Providers** - Prevent cascading failures when AI APIs are down
2. **Implement Plugin Sandboxing** - Critical for security when allowing third-party plugins
3. **Fix Async Streaming Method** - Convert `decide_streaming()` to async or document limitations

### Medium Priority

4. **Centralize Retry Configuration** - Single source of truth for retry policies
5. **Add AIRateLimiter to All Agents** - Currently only AnthropicAgent has rate limiting
6. **Refactor Large Files** - Split `client.py`, `manager.py`, `base.py` into focused modules

### Low Priority

7. **Update Deprecated asyncio Patterns** - Replace `get_event_loop()` with `to_thread()`
8. **Add Service Layer for Storage** - Reduce direct storage access from agents
9. **Document Async Context Requirements** - Clear documentation for RiskManager usage

---

## 6. Appendix: File Reference

### Key Files Reviewed

| File | Purpose | Lines |
|------|---------|-------|
| `/probablyprofit/agent/base.py` | Core agent framework | 817 |
| `/probablyprofit/agent/anthropic_agent.py` | Claude integration | 418 |
| `/probablyprofit/agent/openai_agent.py` | GPT-4 integration | 237 |
| `/probablyprofit/agent/gemini_agent.py` | Gemini integration | 214 |
| `/probablyprofit/agent/ensemble.py` | Multi-agent voting | 409 |
| `/probablyprofit/api/client.py` | Polymarket API client | 1328 |
| `/probablyprofit/api/websocket.py` | Real-time data | 634 |
| `/probablyprofit/api/order_manager.py` | Order lifecycle | 958 |
| `/probablyprofit/api/async_wrapper.py` | Async utilities | 214 |
| `/probablyprofit/api/exceptions.py` | Exception hierarchy | 100 |
| `/probablyprofit/risk/manager.py` | Risk management | 880 |
| `/probablyprofit/storage/database.py` | Database management | 197 |
| `/probablyprofit/storage/repositories.py` | Data access layer | 257 |
| `/probablyprofit/plugins/base.py` | Plugin interfaces | 159 |
| `/probablyprofit/plugins/registry.py` | Plugin discovery | 211 |
| `/probablyprofit/utils/resilience.py` | Error recovery | 539 |

### Architectural Diagrams

```
                    +----------------+
                    |  CLI / Main    |
                    +-------+--------+
                            |
              +-------------+-------------+
              |                           |
      +-------v--------+         +--------v-------+
      |    Agents      |         |   Backtesting  |
      | (AI Decision)  |         |    Engine      |
      +-------+--------+         +----------------+
              |
    +---------+---------+
    |         |         |
+---v---+ +---v---+ +---v---+
|  API  | | Risk  | |Storage|
|Client | |Manager| | Layer |
+---+---+ +---+---+ +---+---+
    |         |         |
    v         v         v
+------+ +--------+ +--------+
|Poly- | |Position| |SQLite/ |
|market| |Tracking| |Postgres|
+------+ +--------+ +--------+
```

---

**Document Version:** 1.0
**Last Updated:** 2026-01-27
