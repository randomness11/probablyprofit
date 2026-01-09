"""
Hook System

Event-driven hooks for plugin lifecycle and trading events.
"""

from typing import Callable, Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger
import asyncio


class Hook(Enum):
    """Available hooks in the trading lifecycle."""
    
    # Lifecycle hooks
    ON_START = "on_start"
    ON_STOP = "on_stop"
    
    # Observation hooks
    BEFORE_OBSERVE = "before_observe"
    AFTER_OBSERVE = "after_observe"
    
    # Decision hooks
    BEFORE_DECIDE = "before_decide"
    AFTER_DECIDE = "after_decide"
    
    # Trade hooks
    BEFORE_TRADE = "before_trade"
    AFTER_TRADE = "after_trade"
    ON_TRADE_ERROR = "on_trade_error"
    
    # Risk hooks
    ON_RISK_CHECK = "on_risk_check"
    ON_RISK_BREACH = "on_risk_breach"
    
    # Data hooks
    ON_MARKET_UPDATE = "on_market_update"
    ON_POSITION_UPDATE = "on_position_update"


@dataclass
class HookHandler:
    """A registered hook handler."""
    callback: Callable
    priority: int = 0
    name: str = ""
    async_handler: bool = True


class HookManager:
    """
    Manages hook registration and execution.
    
    Usage:
        hooks = HookManager()
        
        @hooks.on(Hook.AFTER_TRADE)
        async def log_trade(data):
            print(f"Trade executed: {data}")
            
        # Later:
        await hooks.emit(Hook.AFTER_TRADE, {"price": 0.5})
    """
    
    def __init__(self):
        self._handlers: Dict[Hook, List[HookHandler]] = {
            hook: [] for hook in Hook
        }
    
    def on(
        self,
        hook: Hook,
        priority: int = 0,
        name: str = "",
    ) -> Callable:
        """
        Decorator to register a hook handler.
        
        Args:
            hook: Which hook to listen to
            priority: Execution priority (higher = first)
            name: Optional handler name for debugging
        """
        def decorator(func: Callable) -> Callable:
            handler = HookHandler(
                callback=func,
                priority=priority,
                name=name or func.__name__,
                async_handler=asyncio.iscoroutinefunction(func),
            )
            self._handlers[hook].append(handler)
            # Sort by priority (descending)
            self._handlers[hook].sort(key=lambda h: -h.priority)
            logger.debug(f"Registered hook handler: {handler.name} -> {hook.value}")
            return func
        return decorator
    
    def register(
        self,
        hook: Hook,
        callback: Callable,
        priority: int = 0,
        name: str = "",
    ) -> None:
        """Register a hook handler directly (non-decorator)."""
        handler = HookHandler(
            callback=callback,
            priority=priority,
            name=name or callback.__name__,
            async_handler=asyncio.iscoroutinefunction(callback),
        )
        self._handlers[hook].append(handler)
        self._handlers[hook].sort(key=lambda h: -h.priority)
    
    async def emit(
        self,
        hook: Hook,
        data: Any = None,
        stop_on_false: bool = False,
    ) -> List[Any]:
        """
        Emit a hook event to all handlers.
        
        Args:
            hook: Hook to emit
            data: Data to pass to handlers
            stop_on_false: Stop execution if any handler returns False
            
        Returns:
            List of handler return values
        """
        results = []
        
        for handler in self._handlers[hook]:
            try:
                if handler.async_handler:
                    result = await handler.callback(data)
                else:
                    result = handler.callback(data)
                
                results.append(result)
                
                if stop_on_false and result is False:
                    logger.debug(f"Hook chain stopped by {handler.name}")
                    break
                    
            except Exception as e:
                logger.error(f"Hook handler '{handler.name}' failed: {e}")
                results.append(None)
        
        return results
    
    def clear(self, hook: Optional[Hook] = None) -> None:
        """Clear handlers for a specific hook or all hooks."""
        if hook:
            self._handlers[hook] = []
        else:
            self._handlers = {h: [] for h in Hook}
    
    def list_handlers(self) -> Dict[str, List[str]]:
        """List all registered handlers by hook."""
        return {
            hook.value: [h.name for h in handlers]
            for hook, handlers in self._handlers.items()
            if handlers
        }


# Global hook manager instance
hooks = HookManager()
