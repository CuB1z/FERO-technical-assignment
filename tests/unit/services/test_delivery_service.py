from app.services.delivery_service import SIMULATED_FAILURES, SimulatedDeliveryService

URL = "https://example.com/webhook"
PAYLOAD = {"payment_id": "pay_123"}


async def deliver(service: SimulatedDeliveryService, times: int) -> list[int | None]:
    outcomes: list[int | None] = []
    for _ in range(times):
        try:
            outcomes.append(await service.send(URL, PAYLOAD))
        except TimeoutError:
            outcomes.append(None)
    return outcomes


async def test_same_seed_gives_same_outcomes():
    first = await deliver(SimulatedDeliveryService(failure_rate=0.5, seed=42), 50)
    second = await deliver(SimulatedDeliveryService(failure_rate=0.5, seed=42), 50)

    assert first == second


async def test_outcomes_mix_success_and_known_failures():
    outcomes = await deliver(SimulatedDeliveryService(failure_rate=0.5, seed=1), 200)

    assert 200 in outcomes
    assert set(outcomes) - {200} == set(SIMULATED_FAILURES)


async def test_zero_failure_rate_always_succeeds():
    outcomes = await deliver(SimulatedDeliveryService(failure_rate=0, seed=1), 50)

    assert set(outcomes) == {200}


async def test_full_failure_rate_never_succeeds():
    outcomes = await deliver(SimulatedDeliveryService(failure_rate=1, seed=1), 50)

    assert 200 not in outcomes
