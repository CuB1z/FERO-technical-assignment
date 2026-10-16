from typing import Any

from app.services.delivery_service import DeliveryService


class ScriptedDeliveryService(DeliveryService):
    def __init__(self, *outcomes: int | None):
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send(self, url: str, payload: dict[str, Any]) -> int:
        self.calls.append((url, payload))
        outcome = self._outcomes.pop(0)
        if outcome is None:
            raise TimeoutError
        return outcome
