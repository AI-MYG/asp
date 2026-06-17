# Mac Mini — Pipeline B only (Feishu Inbound)

Checklist for moving **Pipeline B (triage)** to the company Mac Mini while lead
Macs run **lead_tick** (C→D→E→F).

## Prerequisites

- Mac Mini can reach `api.github.com` and has Feishu/ASP Keychain entries:
  `FI_ASP_*` via `scripts/load_asp_env.sh`
- Clone `AI-MYG/asp` (asp-infra layout) to a stable path, e.g.
  `~/CursorWorks/asp-infra`
- Python venv with engine pinned:

```bash
cd ~/CursorWorks/asp-infra
python3 -m venv venv
./venv/bin/pip install -r requirements-feishu-inbound.txt
```

## Install launchd (B only)

On Mac Mini — **only triage**, not lead_tick or C/D/E/F:

```bash
cd ~/CursorWorks/asp-infra
bash launchd/install.sh
launchctl list | grep com.asp.feishu-inbound-triage
```

Optional: unload lead jobs if accidentally installed:

```bash
for label in com.asp.feishu-inbound-lead-tick com.asp.feishu-inbound-agent \
  com.asp.issue-executor com.asp.issue-pr-reviewer com.asp.issue-dev-handback; do
  launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/${label}.plist" 2>/dev/null || true
done
```

## Lead Mac (Marvin / other leads)

1. Keep **lead_tick** (`com.asp.feishu-inbound-lead-tick`) at `:20/:50`
2. Unload **B triage** on lead Mac (Mac Mini owns B):

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.asp.feishu-inbound-triage.plist" 2>/dev/null || true
```

3. Optional: unload legacy separate C/D/E jobs when lead_tick is stable:

```bash
for label in com.asp.feishu-inbound-agent com.asp.issue-executor com.asp.issue-pr-reviewer; do
  launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/${label}.plist" 2>/dev/null || true
done
```

## Verification

1. Create or pick a trivial Feishu inbound issue in `AI-MYG/asp`
2. Within one triage window on Mac Mini: issue gets `triaged` + surface labels
3. Within one lead_tick window on lead Mac: analysis comment appears (Pipeline C)

## Rollback

Re-enable B on lead Mac:

```bash
bash launchd/install.sh   # reloads all plists from config.yaml
```

Disable Mac Mini triage:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.asp.feishu-inbound-triage.plist"
```
