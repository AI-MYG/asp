#!/usr/bin/env bash
# Skip run on Sat/Sun when launchd_schedules.<job>.weekday_only is true in config.yaml.
#
# Usage in run_*.sh:
#   source "$SCRIPT_DIR/pipeline_skip_if_weekend.sh"
#   pipeline_skip_if_weekend agent   # exits 0 on weekend when weekday_only

pipeline_skip_if_weekend() {
  local job="${1:?job name: triage|agent|executor}"
  local script_dir repo_root venv_py wd_only dow
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  repo_root="$(cd "$script_dir/.." && pwd)"
  venv_py="$repo_root/venv/bin/python"
  if [ ! -f "$venv_py" ]; then
    venv_py="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/venv/bin/python"
  fi
  wd_only="$("$venv_py" "$repo_root/launchd/schedule_config.py" weekday-only "$job" 2>/dev/null || echo false)"
  if [ "$wd_only" = "true" ]; then
    dow=$(date +%u)
    if [ "$dow" -gt 5 ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping on weekend (weekday_only=true, job=$job, day=$dow)"
      exit 0
    fi
  fi
}
