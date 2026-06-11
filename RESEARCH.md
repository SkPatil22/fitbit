# How people build for the Fitbit Sense 2 — research notes

*Compiled June 2026.*

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
