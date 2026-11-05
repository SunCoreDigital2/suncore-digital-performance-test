# SunCore Digital Performance Tests (Locust)

Load and performance tests for the SunCore Digital demo website, built with [Locust](https://locust.io) (free, open source).

UI and end-to-end tests live in the separate Playwright repo: `suncore-digital-automation-playwright`.

## What it tests

Two types of simulated user run together, split roughly 3 : 1:

| User | What it does |
|------|--------------|
| **WebsiteUser** | Browses the marketing pages: Home, How it works, Indicative returns, FAQs, Careers, Purchases. Weighted towards the home page. |
| **IRPageUser** | Opens the Indicative Returns page and uses the modeller, calling the data APIs behind it with randomised bundles, scenarios, timeframes and benchmarks. |

IR data endpoints covered:

| Endpoint | Triggered by |
|----------|--------------|
| `/api/ir/kpis` | Changing bundle, timeframe or scenario (Bear / Base / Bull) |
| `/api/ir/modeling` | The earnings curve |
| `/api/ir/benchmarks` | The historical benchmark chart |

These proxy to the IR backend and are much heavier than the page HTML, so watch them separately in the results.

## How the gate is handled

The demo site sits behind the passcode gate. The passcode is redeemed **once** at the start of a run (`POST /api/v1/demo/gate/redeem`) and the gate cookie is shared by every simulated user, so the gate's rate limit isn't hit.

Any request redirected back to the gate is counted as a **failure**, so an expired passcode shows up straight away.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You need a **demo passcode**. Passcodes are created by the Playwright repo's `demoUser` fixture (or by the demo admin) and expire after 1 day.

## Running

**Web UI** (choose users and ramp-up in the browser at http://localhost:8089):

```bash
DEMO_PASSCODE=XXXXXXXX locust -f locustfile.py
```

**Headless** (100 users, ramp 5/sec, 10 minutes, HTML report):

```bash
DEMO_PASSCODE=XXXXXXXX locust -f locustfile.py --headless -u 100 -r 5 -t 10m --html reports/report.html
```

**Single-user baseline** (run this first to separate "slow" from "slow under load"):

```bash
DEMO_PASSCODE=XXXXXXXX locust -f locustfile.py --headless -u 1 -r 1 -t 2m
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEMO_PASSCODE` | (required) | Gate passcode |
| `LOAD_TEST_HOST` | `https://demo.suncoredigital.com` | Target environment |

## Recommended load levels (shared Demo environment)

| Step | Users | Ramp-up | Duration |
|------|-------|---------|----------|
| Smoke | 5 | 1/sec | 1–2 min |
| Light | 25 | 2/sec | 5 min |
| Moderate | 50 | 5/sec | 5–10 min |

**Stop the run if** the failure rate goes above ~1%, p95 response time climbs past ~2–3s or keeps rising, or you see 429 / 503 responses.

## What to look at

- **p95 / p99 response time** per request type: the slowest 5% / 1% of users
- **Failure rate:** non-200 responses and gate redirects
- **Requests per second** at each load level
- The **IR API** rows vs the page rows: the IR data calls are the most likely bottleneck

## Rules

- Get sign-off from the dev team before running anything beyond a smoke test. Load tests can trip WAF/rate limiting and slow the shared demo for everyone.
- Run during quiet periods, not during client demos.
- **Never run against Production** without a planned window.
- Never commit passcodes, tokens or reports containing them.
