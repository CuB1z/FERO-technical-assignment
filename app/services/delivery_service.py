import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any

SIMULATED_FAILURES: tuple[int | None, ...] = (429, 500, 503, 400, None)


class DeliveryService(ABC):
    @abstractmethod
    async def send(self, url: str, payload: dict[str, Any]) -> int:
        pass


class SimulatedDeliveryService(DeliveryService):
    def __init__(
        self,
        *,
        failure_rate: float,
        max_latency_seconds: float = 0.0,
        seed: int | None = None,
    ):
        self._failure_rate = failure_rate
        self._max_latency_seconds = max_latency_seconds
        self._random = random.Random(seed)

    async def send(self, url: str, payload: dict[str, Any]) -> int:
        await asyncio.sleep(self._random.uniform(0, self._max_latency_seconds))
        if self._random.random() >= self._failure_rate:
            return 200
        status_code = self._random.choice(SIMULATED_FAILURES)
        if status_code is None:
            raise TimeoutError(f"Simulated timeout delivering to {url}")
        return status_code
