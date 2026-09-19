#!/usr/bin/env bash
# Run a command in a pixi environment:  scripts/pixi-run.sh <env> <command...>
# For moon tasks that take `moon run <task> -- <args>`: `script` tasks drop
# those args, so such tasks are `command: bash` + this (as run-mjpython.sh).
set -euo pipefail
. ./scripts/pixi-path.sh
env="$1"
shift
exec pixi run --environment "$env" -- "$@"
