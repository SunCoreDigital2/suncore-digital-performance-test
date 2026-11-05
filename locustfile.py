"""
Load test for the SunCore Digital demo website.

The demo site sits behind the passcode gate (nginx checks a gate cookie). To avoid
hitting the gate's rate limit with every simulated user, the passcode is redeemed
ONCE at the start of the run and the resulting cookie is shared by all users.

Usage (from the repo root):
    pip install -r requirements.txt
    DEMO_PASSCODE=XXXXXXXX locust -f locustfile.py

Headless example (100 users, ramp 5/sec, 10 minutes, HTML report):
    DEMO_PASSCODE=XXXXXXXX locust -f locustfile.py --headless \
        -u 100 -r 5 -t 10m --html reports/report.html

Get a passcode by running any Playwright test that uses the demoUser fixture,
or ask for one from the demo admin. Passcodes expire after 1 day.

Never run against prod - This is super important as it will affect paid users
"""
import os
import random

import requests
from locust import HttpUser, between, events, task

HOST = os.getenv("LOAD_TEST_HOST", "https://demo.suncoredigital.com")
DEMO_PASSCODE = os.getenv("DEMO_PASSCODE", "")

# Filled once in on_test_start and copied into every simulated user's session
GATE_COOKIES: dict[str, str] = {}


@events.test_start.add_listener
def unlock_gate_once(environment, **kwargs):
    """Redeem the passcode once and keep the gate cookie for all users."""
    if not DEMO_PASSCODE:
        raise SystemExit("Set DEMO_PASSCODE to a valid demo passcode before running.")

    session = requests.Session()
    response = session.post(
        f"{HOST}/api/v1/demo/gate/redeem",
        json={"passcode": DEMO_PASSCODE},
        timeout=30,
    )
    if response.status_code == 429:
        raise SystemExit("Gate rate limit hit (429). Wait a few minutes and try again.")
    if not response.ok:
        raise SystemExit(f"Gate did not unlock: HTTP {response.status_code} {response.text[:200]}")

    GATE_COOKIES.update(session.cookies.get_dict())
    if not GATE_COOKIES:
        raise SystemExit("Gate redeemed but no cookie was returned; check the gate API.")


class WebsiteUser(HttpUser):
    """Visitor browsing the marketing pages."""
    weight = 3
    host = HOST
    wait_time = between(1, 5)  # think time between page views

    def on_start(self):
        for name, value in GATE_COOKIES.items():
            self.client.cookies.set(name, value)

    def _get(self, path: str, name: str):
        # Fail the request if we've been bounced back to the gate instead of the real page
        with self.client.get(path, name=name, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
            elif "/gate" in response.url:
                response.failure("Redirected to the gate (cookie missing or expired)")

    # Weights mimic real traffic: most visitors land on the home page
    @task(5)
    def home(self):
        self._get("/", "Home")

    @task(2)
    def how_it_works(self):
        self._get("/howitworks", "How it works")

    @task(2)
    def indicative_returns(self):
        self._get("/indicative", "Indicative returns")

    @task(1)
    def faqs(self):
        self._get("/faqs", "FAQs")

    @task(1)
    def careers(self):
        self._get("/careers", "Careers")

    @task(1)
    def purchases(self):
        self._get("/purchases", "Purchases")


# ---------------------------------------------------------------------------
# Indicative Returns (IR) page data
# ---------------------------------------------------------------------------
# The IR page loads its figures in the browser from three same-origin routes
# (/api/ir/kpis, /api/ir/modeling, /api/ir/benchmarks). These proxy to the IR
# backend, so they are much heavier than the page HTML and are what makes the IR
# page feel slow. The routes require the IR email-capture cookie.
IR_ACCESS_COOKIE = ("sc_ir_access", "verified")

BUNDLES = ["s23", "s21"]
BUNDLE_IDS = {"s23": "s23_hyd", "s21": "s21e_xp"}
SCENARIOS = ["bear", "base", "bull"]
TIMEFRAMES = ["1Y", "3Y", "5Y", "10Y"]
LOOKBACKS = ["1y", "3y", "5y", "10y"]
BENCHMARKS = ["S&P 500", "NASDAQ-100", "Oil (Brent)", "Gold (GLD)"]


class IRPageUser(HttpUser):
    """Visitor using the Indicative Returns modeller (switching scenarios, lookbacks, benchmarks)."""
    weight = 1
    host = HOST
    wait_time = between(2, 6)

    def on_start(self):
        for name, value in GATE_COOKIES.items():
            self.client.cookies.set(name, value)
        self.client.cookies.set(*IR_ACCESS_COOKIE)
        # Opening the page fires the initial data loads
        self.client.get("/indicative", name="IR page")

    def _get_json(self, path: str, params, name: str):
        with self.client.get(path, params=params, name=name, catch_response=True) as response:
            if response.status_code == 401:
                response.failure("IR access cookie rejected (401)")
            elif response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")

    @task(3)
    def kpis(self):
        # Fired when the user changes bundle / timeframe / scenario
        bundle = random.choice(BUNDLES)
        self._get_json("/api/ir/kpis", {
            "bid": BUNDLE_IDS[bundle],
            "tf": random.choice(TIMEFRAMES),
            "sc": random.choice(SCENARIOS),
            "cl": "false",
        }, "IR API: kpis")

    @task(2)
    def modeling(self):
        self._get_json("/api/ir/modeling", {
            "lookback": random.choice(LOOKBACKS),
            "bundle": random.choice(BUNDLES),
            "benchmark": random.choice(BENCHMARKS),
        }, "IR API: modeling")

    @task(2)
    def benchmarks(self):
        self._get_json("/api/ir/benchmarks", [
            ("timeframe", random.choice(TIMEFRAMES)),
            ("benchmarks", "BTC Spot"),
            ("benchmarks", random.choice(BENCHMARKS)),
        ], "IR API: benchmarks")
