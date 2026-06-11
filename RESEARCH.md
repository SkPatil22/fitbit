# How people build for the Fitbit Sense 2 — research notes

*Compiled June 2026. Wave 2 (X/Reddit-sourced ideas) appended in §5.*

## 1. The hard constraint: no third-party apps on the watch

The Sense 2 / Versa 4 generation dropped the Fitbit OS SDK. Google's position
is that these are "health and wellness focused devices" and third-party apps
are not coming back; only **clock faces** remain open to developers
([9to5Google](https://9to5google.com/2023/02/17/fitbit-studio/),
[Fitbit Community thread](https://community.fitbit.com/t5/SDK-Development/Sense-2-SDK-amp-Apps/td-p/5377001)).

Hackers have produced **unofficial sideloading** routes —
[cmengler/fitbit-app-versa4](https://github.com/cmengler/fitbit-app-versa4) and
[yeohongred/fitbit-versa4-sense2-sdk](https://github.com/yeohongred/fitbit-versa4-sense2-sdk) —
but they're fragile, unsupported, and can break with firmware updates. Not a
foundation to build on.

## 2. The real platform: the Fitbit Web API

What everyone actually builds against is the
[Web API](https://dev.fitbit.com/build/reference/web-api/). The key unlock: a
free **"Personal" app type** grants
[intraday access](https://dev.fitbit.com/build/reference/web-api/intraday/) to
your own data with no approval process:

| Data | Granularity | Endpoint family |
|---|---|---|
| Heart rate | 1 sec / 1 min / 5 min / 15 min | `activities/heart/.../1d/1min` |
| Steps, calories, AZM | 1 min | `activities/steps/...` |
| HRV (RMSSD) | nightly + 5-min intraday | `hrv/date/...` |
| Breathing rate | nightly | `br/date/...` |
| SpO₂ | nightly + minute-level | `spo2/date/...` |
| Skin temperature | nightly deviation | `temp/skin/date/...` |
| Sleep stages | per sleep log | `1.2/.../sleep/date/...` |
| ECG readings | per reading | `ecg/list` |
| Cardio fitness (VO₂max) | daily | `cardioscore/date/...` |

Notable: HRV, SpO₂ and breathing rate were added as first-class API data types
in [Dec 2022](https://dev.fitbit.com/blog/2022-12-06-announcing-new-data-types/).
Auth is OAuth 2.0 with PKCE. Rate limit: 150 requests/hour/user. There is
**no real-time push** — data arrives when the watch syncs
([community request thread](https://community.fitbit.com/t5/SDK-Development/feature-request-real-time-API-to-retrieve-heart-rate-and-steps/td-p/2700423)).
The watch's native EDA/stress score is **not** in the public API.

## 3. Creative things the community builds (social media / blogs / GitHub)

1. **Stress trackers from HR + HRV** — the use case you saw tweeted. Since the
   EDA score isn't exposed, people reconstruct stress: e.g. the KAIST
   [Anti-Stress-Tracker](https://github.com/maria-korosteleva/Anti-Stress-Tracker)
   estimates stress from heart-rate-variability (Baevsky stress index) via the
   Web API + Flask. → **implemented here as `sense2/stress.py`** (HR-above-resting
   masked by step activity, modulated by HRV baseline deviation).
2. **Illness early-warning** — the famous result from
   [Stanford Medicine](https://med.stanford.edu/news/all-news/2020/12/smartwatch-can-detect-early-signs-of-illness.html)
   and [Nature BME](https://www.nature.com/articles/s41551-020-00640-6):
   resting-HR anomalies flag infection 4–7 days before symptoms (63% of COVID
   cases pre-symptomatically). Hobbyists replicate this on their own data.
   → **implemented as `sense2/health_alerts.py`** (z-score anomalies on resting
   HR ↑, breathing rate ↑, skin temp ↑, HRV ↓; two-tier WATCH/ALERT).
3. **Readiness / recovery scores** — Whoop & Oura charge subscriptions for
   this; Fitbit paywalls theirs behind Premium. People rebuild it from HRV +
   resting HR + sleep. → **implemented as `sense2/readiness.py`**.
4. **Life dashboards** — e.g. [Andy Kong's Fitbit API writeup](https://andykong.org/blog/fitbit1/)
   pipes minute-level HR into personal dashboards. → **implemented as the
   Flask dashboard in `sense2/dashboard/`**.
5. **Smart-home / workflow automation** — the official
   [Home Assistant integration](https://www.home-assistant.io/integrations/fitbit/),
   [n8n](https://n8n.io/integrations/fitbit/and/home-assistant/) and
   [Pipedream](https://pipedream.com/apps/fitbit/integrations/home-assistant)
   recipes (lights when you wake, notifications on goals). → the `FitbitClient`
   + SQLite export here are the building blocks for this.
6. **Data archival/export** — because fine-grained API access is windowed and
   rate-limited, people keep local copies (the
   [fitbitViz](https://cran.r-project.org/web/packages/fitbitViz/vignettes/fitbit_viz.html)
   R package, assorted `fitbit-api` GitHub topics). → **implemented as
   `sense2/export.py`** (SQLite + CSV).

## 4. What that meant for this repo

Everything feasible without hacking watch firmware is implemented and tested
in demo mode; plugging in real credentials (README) swaps the synthetic client
for the live API with the identical interface.

## 5. Wave 2 — ideas mined from X and Reddit culture

Direct crawling of x.com and reddit.com is blocked, so these were gathered
through secondary coverage, search snippets and the open-source projects the
threads point at.

1. **"My heart rate during X" graphs** — a persistent viral genre on X/TikTok:
   HR traces during horror movies, proposals, interviews, penalty shootouts.
   Fitbit itself leaned in, hiring a paid "Horror Heart Rate Analyst" to watch
   13 horror films on-device ([Athletech](https://athletechnews.com/fitbit-conducting-horror-movie-heart-rate-study/),
   [AV Club](https://www.avclub.com/a-company-is-willing-to-pay-you-1-300-to-watch-13-horr-1847672079));
   bloggers chart movie-night HR ([racery](https://racery.com/blog/2017/01/06/fitbit-charge-wild-heart-calm-mind/)).
   → `sense2/sessions.py` + `session` CLI (stats, spike timestamps, shareable card).
2. **n=1 experiments** (r/QuantifiedSelf): does alcohol/caffeine/late training
   tank my HRV? WHOOP's published population numbers (one drink ≈ HRV −7 ms,
   RHR +3 bpm) made this mainstream
   ([Outside Online](https://www.outsideonline.com/health/running/gear/health-gear/lcohol-hrv-resting-heart-rate-sleep/)).
   → `sense2/journal.py`: tag days, compare following-night biometrics with
   effect sizes and a significance heuristic.
3. **Training load without the subscription** — Fitbit's "Cardio Load" is a
   modified Banister TRIMP over heart-rate reserve, Premium-only
   ([Fitbit help](https://support.google.com/fitbit/answer/15402655?hl=en-GB),
   [arXiv](https://arxiv.org/html/2508.11613v1)); open implementations:
   [choochoo](https://andrewcooke.github.io/choochoo/impulse.html),
   [ff-perf](https://github.com/jjjkkkjjj/ff-perf),
   [mechgt/training-load](https://github.com/mechgt/training-load).
   → `sense2/training.py`: minute-level TRIMP + CTL/ATL/TSB with first-week
   seeding.
4. **Sleep regularity / social jetlag** — SRI (probability of same sleep state
   24h apart) and social jetlag (free-vs-work-day sleep midpoint) are the two
   research metrics the self-tracking crowd keeps reimplementing
   ([Sleep as Android docs](https://sleep.urbandroid.org/docs/sleep/chrono_jetlag.html),
   [Wikipedia](https://en.wikipedia.org/wiki/Social_jetlag),
   [SLEEP Advances](https://academic.oup.com/sleepadvances/article/6/Supplement_1/A18/8271604)).
   → `sense2/sleep_rhythm.py`.
5. **Skin-temperature shift tracking** — big topic on the Fitbit forums; wrist
   temperature surges match ovulation in ~82% of cycles, and fevers show the
   same signature ([Wareable](https://www.wareable.com/fitbit/fitbit-skin-temperature-readings-set-for-huge-accuracy-boost),
   [community thread](https://community.fitbit.com/t5/Sleep-Well/Skin-Temperature-interpretation/td-p/5594737)).
   → `sense2/temp_rhythm.py`: sustained-shift detector with a baseline that
   excludes already-elevated nights.
6. **Calendar heatmaps & "Wrapped" posts** (r/dataisbeautiful) — e.g.
   [erramirez/fitbitcalendar](https://github.com/erramirez/fitbitcalendar).
   → `sense2/report.py`: standalone HTML with GitHub-style steps heatmap,
   records and streaks.
7. **Self-hosted pipelines** — the most-starred community pattern is
   Fitbit → InfluxDB → Grafana
   ([arpanghosh8453/fitbit-grafana](https://github.com/arpanghosh8453/fitbit-grafana),
   [LeoMcA/fitbit-grafana](https://github.com/LeoMcA/fitbit-grafana),
   [gofit](https://github.com/timatooth/gofit),
   [Grafana dashboard](https://grafana.com/grafana/dashboards/12348-fitbit-api-exporter/)),
   plus Home Assistant automation chatter. → `sense2/automations.py` webhook
   bridge (works with HA/n8n/IFTTT) on top of the existing SQLite/CSV export.
8. **Recovery-score sharing culture** — Whoop/Oura recovery screenshots beside
   Strava activities normalized treating readiness as a social, shareable
   number ([Strava×Oura](https://support.strava.com/hc/en-us/articles/6619564102157-Oura-and-Strava),
   [athletedata](https://the5krunner.com/2026/04/30/athletedata-ai-coach/)) —
   the readiness module plus the report/session cards cover the shareable-artifact side.

## 6. Wave 3 — Fitbit Premium feature research

What Premium (renamed "Google Health Premium" in May 2026) actually gates, and
feasibility of recreating each from Web API data:

- **Gemini Personal Health Coach** — the headline 2025/26 Premium feature: an
  all-in-one trainer/sleep coach/wellness advisor that builds custom workout
  routines from your goals and data
  ([TechCrunch](https://techcrunch.com/2025/10/27/fitbits-revamped-app-with-gemini-powered-health-coach-rolls-out-to-premium-users/),
  [Google blog](https://blog.google/products-and-platforms/devices/fitbit/personal-health-coach-public-preview/),
  [Android Central](https://www.androidcentral.com/wearables/fitbit/new-fitbit-personal-health-coach-preview-arrives-tomorrow-heres-how-it-works)).
  → recreated as `sense2/coach.py`: Claude Haiku 4.5 chat grounded in the
  repo's computed metrics, with tool-use escalation to Claude Sonnet 4.6 for
  plans and deep analysis.
- **Sleep Profile** — monthly analysis across 10 sleep metrics assigning one
  of six "sleep animals" ([WearableBeat](https://wearablebeat.com/articles/fitbit-premium-vs-free-is-the-subscription-worth-it/)).
  → recreated as `sense2/sleep_profile.py` from duration, midpoint
  consistency, deep/REM share and efficiency.
- **Daily Readiness, Cardio Load, stress details, Wellness Report** — already
  recreated in waves 1–2 (`readiness.py`, `training.py`, `stress.py`,
  `report.py`).
- **Snore & noise detection** — requires the watch microphone at night; no
  API surface exists, so it cannot be recreated off-device.

### Sources

- https://9to5google.com/2023/02/17/fitbit-studio/
- https://community.fitbit.com/t5/SDK-Development/Sense-2-SDK-amp-Apps/td-p/5377001
- https://github.com/cmengler/fitbit-app-versa4
- https://github.com/yeohongred/fitbit-versa4-sense2-sdk
- https://dev.fitbit.com/build/reference/web-api/
- https://dev.fitbit.com/build/reference/web-api/intraday/
- https://dev.fitbit.com/blog/2022-12-06-announcing-new-data-types/
- https://github.com/maria-korosteleva/Anti-Stress-Tracker
- https://med.stanford.edu/news/all-news/2020/12/smartwatch-can-detect-early-signs-of-illness.html
- https://www.nature.com/articles/s41551-020-00640-6
- https://www.mobihealthnews.com/news/early-data-fitbit-study-indicates-it-can-predict-covid-19-symptoms-show
- https://www.home-assistant.io/integrations/fitbit/
- https://n8n.io/integrations/fitbit/and/home-assistant/
- https://andykong.org/blog/fitbit1/
- https://cran.r-project.org/web/packages/fitbitViz/vignettes/fitbit_viz.html
