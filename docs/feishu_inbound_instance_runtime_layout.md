# Feishu Inbound Instance Runtime Layout (`var/feishu_inbound`)

**Date:** 2026-06-17  
**Status:** Done  
**Related:** feishu-inbound-skill RFC-001 Amendment 2026-06-17; `tools/feishu_inbound/config.yaml`; rootgrove `config/feishu_inbound_personal.yaml`

## Problem

Pipeline B–F write **runtime checkpoints** (`issue_scanner_state.json`, executor/reviewer locks, triage state). These are not documentation and must not be committed.

Two bugs caused **ASP runtime state to land in rootgrove monorepo root**:

1. Engine `state_dir` was resolved from **process cwd**, while `logs_dir` was resolved from **config file directory**.
2. ASP config used `../../state/feishu_inbound`, which with wrong cwd became `rootgrove/state/feishu_inbound/` (e.g. after manual `run_cli.sh scan` from the engine repo).

**Principle:** State belongs to the **pipeline instance** (who runs B–F), not the **surface repo** (asp-backend/app). An issue in `AI-MYG/asp-backend` still stores checkpoint JSON under **ASP instance** (`AI-MYG/asp`).

## Decision

| Layer | Runtime root | Gitignore |
|-------|--------------|-----------|
| **ASP instance** | `var/feishu_inbound/{state,logs}/` (this repo) | `var/` in `.gitignore` |
| **Personal instance** | `var/feishu_inbound/{state,logs}/` (rootgrove) | `var/` + `state/` fallback |
| **Surface repos** | — | No feishu inbound state |

Launchd stdout/stderr for `com.asp.*` remain at `logs/*.log` (process logs). Engine `logs_dir` under `var/feishu_inbound/logs/` holds pipeline subcommand logs from `launchd.py` / scanner / executor.

## Config paths (relative to config YAML)

**ASP** (`tools/feishu_inbound/config.yaml`):

```yaml
state_dir: ../../var/feishu_inbound/state
logs_dir: ../../var/feishu_inbound/logs
worktree_dir: ../../worktrees
```

**Personal** (rootgrove `config/feishu_inbound_personal.yaml`):

```yaml
state_dir: ../var/feishu_inbound/state
logs_dir: ../var/feishu_inbound/logs
worktree_dir: ../worktrees/feishu_inbound
```

## Engine change

`EngineConfig.resolve_path()` — all instance paths anchor to **config file parent**, not cwd. Pin engine after merge (`feishu-inbound-skill` branch `issue-1/m1-engine-migration`, commit `35b83a0+`).

## Migration (2026-06-17)

- Moved `rootgrove/state/feishu_inbound/issue_scanner_state.json` → `var/feishu_inbound/state/` (local, gitignored)
- Removed `rootgrove/state/`

## Verification

```bash
cd projects/feishu-inbound-skill
.venv/bin/pytest tests/test_config_paths.py -q
```

## Do not

- Put checkpoints under surface worktrees (`asp-backend`, `app`, `qmt`).
- Commit `var/` or `state/` under any repo.
