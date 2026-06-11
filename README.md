# Sense 2 Companion

Analytics and tooling for the **Fitbit Sense 2**, built on the Fitbit Web API.

The Sense 2 famously **does not support third-party on-device apps** — Google
removed the Fitbit OS SDK for Sense 2/Versa 4 and only allows clock faces. So
this project does what the community does instead: it pulls the rich biometric
data the watch records (1-minute heart rate, HRV, SpO₂, breathing rate, skin
temperature, sleep stages, ECG) through the **Web API** and builds the features
the watch itself doesn't give you. See [RESEARCH.md](RESEARCH.md) for the full
write-up of what's possible and what the community is building.

## Features

| Feature | Module | What it does |
|---|---|---|
| **Stress tracker** | `sense2/stress.py` | Intraday 0–100 stress curve from HR elevation above resting while *not* moving (steps mask exercise), amplified when daily HRV is suppressed vs your baseline. Detects sustained stress episodes ("⚡ 11:06–11:45, peak 73"). |
| **Readiness score** | `sense2/readiness.py` | Whoop/Oura-style daily recovery score: HRV vs 30-day baseline (40%) + resting HR vs baseline (30%) + sleep duration/efficiency (30%), with a recommendation. |
| **Illness early-warning** | `sense2/health_alerts.py` | Stanford-study-style anomaly detection: flags days when resting HR, breathing rate or skin temp are elevated (or HRV suppressed) ≥2σ beyond your trailing baseline. 1 signal → WATCH, 2+ → ALERT. |
| **Web dashboard** | `sense2/dashboard/` | Flask + dependency-free SVG charts: readiness gauge, intraday HR/stress chart with activity bands, sleep stages, nightly vitals, 30-day trend sparklines, alert banner. |
| **Local archive & export** | `sense2/export.py` | Sync daily metrics (incl. computed stress/readiness) into SQLite and export CSV — your data outlives the API's trailing window. |
| **OAuth 2.0 + PKCE** | `sense2/auth.py` | One-command authorization against a free "Personal" Fitbit dev app, with token persistence and auto-refresh. |
| **Full API client** | `sense2/client.py` | Normalized access to every Sense 2 data type: intraday HR/steps, HRV, sleep, SpO₂, breathing rate, skin temp, ECG, VO₂max. |
| **Demo mode** | `sense2/demo_data.py` | Deterministic synthetic data (including a simulated illness onset) so everything runs without a Fitbit account. |

## Quickstart (no Fitbit account needed)

```bash
pip install -r requirements.txt

python -m sense2 dashboard --demo          # http://127.0.0.1:5000
python -m sense2 stress    --demo          # intraday stress in the terminal
python -m sense2 readiness --demo
python -m sense2 alerts    --demo          # demo simulates an illness onset
python -m sense2 export    --demo --days 30
```

## Connecting your real Sense 2

1. Register a free app at <https://dev.fitbit.com/apps> →
   * **OAuth 2.0 Application Type:** `Personal` (this unlocks intraday data for your own account)
   * **Redirect URL:** `http://localhost:8765/auth/callback`
2. Export your credentials and authorize once:

   ```bash
   export FITBIT_CLIENT_ID=XXXXXX
   export FITBIT_CLIENT_SECRET=yyyy        # optional with PKCE
   python -m sense2 auth                   # opens browser, saves ~/.sense2/tokens.json
   ```

3. Run any command without `--demo`:

   ```bash
   python -m sense2 dashboard
   python -m sense2 alerts
   ```

Note: the API allows **150 requests/hour**; `export --days 90` paces through it.
The watch syncs to Fitbit's cloud via your phone, so data lags the watch by one
sync (this is the platform's limit — there is no real-time push API).

## Running tests

```bash
python -m pytest tests/ -q     # 20 tests, all offline via demo mode
```

## Limitations (platform, not this code)

* No on-device apps/notifications — the Sense 2 can't run custom code; everything here is off-device.
* The watch's native EDA-based stress score isn't exposed by the public API, which is exactly why the community (and this repo) reconstructs stress from HR + HRV.
* HRV/breathing/SpO₂/skin temp are measured during sleep, so those signals update once per day.
* Stress, readiness and health alerts are heuristics for self-tracking — not medical advice.
