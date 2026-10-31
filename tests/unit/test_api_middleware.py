"""The API's ConcurrencyLimit and SecurityHeaders middleware (Phase 15g), on a tiny app of their own."""

import asyncio
import concurrent.futures

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.app.main import ConcurrencyLimit, SecurityHeaders


def make_app(limit=2, max_wait=0.2, work=0.3):
    inside, peak = [0], [0]

    async def slow(request):
        inside[0] += 1
        peak[0] = max(peak[0], inside[0])
        await asyncio.sleep(work)
        inside[0] -= 1
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", slow)])
    app.add_middleware(ConcurrencyLimit, limit=limit, max_wait=max_wait)
    app.add_middleware(SecurityHeaders)
    return app, peak


def run(coro):
    """Run `coro` on a fresh thread: in the full suite, Playwright's sync API keeps an event loop
    running on the test thread, where starting another one is refused."""
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def burst(app, n):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await asyncio.gather(*(client.get("/") for _ in range(n)))


def test_never_more_than_the_limit_inside():
    app, peak = make_app(limit=3, max_wait=5, work=0.05)
    responses = run(burst(app, 20))
    assert [r.status_code for r in responses] == [200] * 20  # everyone served, in turn
    assert peak[0] == 3


def test_waiting_too_long_is_503_with_retry_after_and_security_headers():
    app, _ = make_app(limit=1, max_wait=0.1, work=0.5)
    statuses = sorted(r.status_code for r in run(burst(app, 3)))
    assert statuses == [200, 503, 503]
    busy = next(r for r in run(burst(app, 2)) if r.status_code == 503)
    assert busy.json() == {"detail": "Server busy"}
    assert busy.headers["retry-after"] == "1"
    assert busy.headers["x-content-type-options"] == "nosniff"


def test_a_slot_is_released_even_when_the_endpoint_fails():
    async def boom(request):
        raise RuntimeError("endpoint crashed")

    app = Starlette(routes=[Route("/", boom)])
    app.add_middleware(ConcurrencyLimit, limit=1, max_wait=0.2)

    async def three_requests():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            return [(await client.get("/")).status_code for _ in range(3)]

    assert run(three_requests()) == [500, 500, 500]  # never 503: the slot came back each time


def test_existing_headers_are_not_duplicated():
    async def custom(request):
        return JSONResponse({}, headers={"Cache-Control": "max-age=60"})

    app = Starlette(routes=[Route("/", custom)])
    app.add_middleware(SecurityHeaders)
    response = run(burst(app, 1))[0]
    assert response.headers.get_list("cache-control") == ["max-age=60"]
