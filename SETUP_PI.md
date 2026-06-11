# Raspberry Pi setup — Sense 2 Companion

**Audience: a Claude (Code) instance running on the Raspberry Pi with shell
access.** Execute the steps in order. Each step has a verification — do not
move on until it passes. Steps marked **[ASK USER]** need input only the
owner can provide; ask, then continue.

The end state: the Sense 2 dashboard served at `http://<pi>:8400` on the
local network, syncing Fitbit data hourly, auto-starting on boot via systemd.

---

## 0. Preflight

```bash
python3 --version        # need >= 3.10 (Raspberry Pi OS Bookworm ships 3.11)
ping -c1 api.fitbit.com  # network reachability
echo "$USER" && echo "$HOME"
```

If Python is older than 3.10, stop and tell the user to update Raspberry Pi
OS first. Any Pi model works (the suite is lightweight — pure Python, SQLite,
a few API calls per hour); on a Pi Zero just expect slower page loads.

## 1. Install

```bash
sudo apt-get update && sudo apt-get install -y git python3-venv
git clone https://github.com/SkPatil22/fitbit.git ~/sense2-companion
python3 -m venv ~/sense2-venv
~/sense2-venv/bin/pip install ~/sense2-companion
```

**Verify:** `~/sense2-venv/bin/sense2 readiness --demo` prints a readiness
score. Optionally run the test suite:
`~/sense2-venv/bin/pip install pytest && cd ~/sense2-companion && ~/sense2-venv/bin/python -m pytest tests/ -q`
(all tests should pass, no network needed).

## 2. Smoke-test the server in demo mode

```bash
~/sense2-venv/bin/sense2 server --demo --sync-interval 0 &
sleep 3
curl -s http://127.0.0.1:8400/api/overview | head -c 200   # expect JSON
kill %1
```

## 3. [ASK USER] Fitbit API credentials

Ask the user to register a (free) Fitbit app — this is a browser task only
they can do:

1. Go to <https://dev.fitbit.com/apps/new> (sign in with the Fitbit/Google
   account the Sense 2 is paired to).
2. Fill anything reasonable for name/description/URLs, **except**:
   - **OAuth 2.0 Application Type: `Personal`** (this is what unlocks
     intraday data)
   - **Redirect URL: `http://localhost:8765/auth/callback`** (exact string)
3. Have them paste back the **Client ID** and **Client Secret**.

Store them (mode 600):

```bash
mkdir -p ~/.sense2 && chmod 700 ~/.sense2
cat > ~/.sense2/env <<EOF
FITBIT_CLIENT_ID=<paste>
FITBIT_CLIENT_SECRET=<paste>
EOF
chmod 600 ~/.sense2/env
```

## 4. [ASK USER] One-time OAuth authorization

The auth flow needs a browser hitting `localhost:8765` — the Pi is headless,
so pick whichever path fits how the user is connected:

**Path A — SSH port forward (preferred when the user SSHes in):**
1. Tell the user to reconnect with: `ssh -L 8765:localhost:8765 <user>@<pi>`
2. On the Pi run:
   `set -a && source ~/.sense2/env && set +a && ~/sense2-venv/bin/sense2 auth`
3. It prints an `https://www.fitbit.com/oauth2/authorize?...` URL — give it
   to the user to open **in the browser on their laptop**. After they click
   Allow, the callback rides the SSH tunnel to the Pi and tokens are saved to
   `~/.sense2/tokens.json`.

**Path B — authorize elsewhere, copy tokens:** the user runs
`python -m sense2 auth` on their desktop (same repo, same env vars), then
copies the file: `scp ~/.sense2/tokens.json <user>@<pi>:~/.sense2/`.

**Verify (real data, no `--demo`):**

```bash
set -a && source ~/.sense2/env && set +a
~/sense2-venv/bin/sense2 readiness
```

A real readiness score = auth works and tokens auto-refresh from here on.

## 5. [ASK USER] Optional: AI coach

The dashboard's coach chat needs an Anthropic API key
(<https://platform.claude.com>). Ask whether they want it; if yes, append to
the env file:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> ~/.sense2/env
```

If no, skip — everything else works without it and the coach panel will
explain how to enable it later.

## 6. Install the systemd service

```bash
sed -e "s|__USER__|$USER|g" -e "s|__HOME__|$HOME|g" \
    ~/sense2-companion/deploy/sense2.service | sudo tee /etc/systemd/system/sense2.service
sudo systemctl daemon-reload
sudo systemctl enable --now sense2
```

**Verify:**

```bash
systemctl status sense2 --no-pager        # active (running)
curl -s http://127.0.0.1:8400/ | head -c 100   # HTML
journalctl -u sense2 -n 20 --no-pager     # "dashboard listening", "sync ok"
```

Then reboot-test once: `sudo reboot`, reconnect, confirm
`systemctl is-active sense2` says `active`.

## 7. Hand off to the user

Tell the user:
- Dashboard: `http://<pi-hostname>.local:8400` (or `http://<pi-ip>:8400`)
  from any device on their network.
- Data lands hourly in `~/.sense2/sense2.db` + `sense2_daily.csv`.
- CLI anytime: `~/sense2-venv/bin/sense2 stress|readiness|alerts|training|rhythm|profile|report|coach`.
- Logs: `journalctl -u sense2 -f`.

**Security note (tell the user):** the dashboard has no login and exposes
health data — it binds to the LAN, which is fine on a trusted home network,
but do **not** port-forward 8400 to the internet. For remote access suggest
Tailscale/WireGuard.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `429` / rate-limit warnings in logs | Normal if hammering CLI + server together; Fitbit allows 150 req/hr. The sync loop retries next cycle on its own. |
| `Not authorized yet` | Re-run step 4; check `~/.sense2/tokens.json` exists and is owned by the service user. |
| Token refresh fails after long downtime | Fitbit refresh tokens are single-use but long-lived; if truly expired re-run `sense2 auth` (step 4). |
| Port 8400 in use | `sense2 server --port <other>` and update the unit file. |
| Dashboard empty for today | The watch only syncs to Fitbit's cloud when the phone app runs — open the Fitbit app to force a sync. |
| Coach replies 503 | `ANTHROPIC_API_KEY` missing/invalid in `~/.sense2/env`; restart service after editing (`sudo systemctl restart sense2`). |
| Service won't start | `journalctl -u sense2 -n 50` — usually a path typo in the unit file from step 6. |
