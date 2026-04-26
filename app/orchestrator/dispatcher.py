"""Event dispatcher using handler map."""

from collections.abc import Awaitable, Callable

from app.orchestrator.events import Event

EventHandler = Callable[[Event], Awaitable[None]]


class EventDispatcher:
    """Map event type to handlers and dispatch events."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        """Register event handler for event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, event: Event) -> None:
        """Dispatch event to all handlers."""
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            await handler(event)
