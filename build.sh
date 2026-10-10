#!/usr/bin/env bash
#
# build.sh - build the current janito source into the global `janito-latest`
# install so you can simply run `janito-latest` afterwards (e.g. resume a
# session with `janito-latest -C`).
#
# Usage:
#   ./build.sh
#
# What it does:
#   1. Builds the *current* working tree (the checked-out branch/commit,
#      uncommitted changes included) with uv into the `janito-latest`
#      virtualenv (created on first run).
#   2. Refreshes the `~/.local/bin/janito-latest` symlink to that venv.
#   3. Prints the resulting version (setuptools-scm derives it from the
#      latest git tag + commit distance + short hash).
#
# The install is non-editable: the source is copied into the venv, so
# re-run this script after pulling / switching branches / editing code.
#
# Overridable environment variables:
#   JANITO_LATEST_VENV    path of the virtualenv (default ~/.venvs/janito-latest)
#   JANITO_LATEST_BIN_DIR directory of the launcher  (default ~/.local/bin)
#   JANITO_LATEST_PYTHON  interpreter used to create a fresh venv
#                         (default: `python3` found on PATH)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${JANITO_LATEST_VENV:-$HOME/.venvs/janito-latest}"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_JANITO="$VENV_DIR/bin/janito"
BIN_DIR="${JANITO_LATEST_BIN_DIR:-$HOME/.local/bin}"
BIN_LINK="$BIN_DIR/janito-latest"
PYTHON_BIN="${JANITO_LATEST_PYTHON:-python3}"

say() { printf '%s\n' "$*"; }
die() { printf 'build.sh: error: %s\n' "$*" >&2; exit 1; }

# --- sanity checks ----------------------------------------------------------
[ -f "$REPO_ROOT/pyproject.toml" ] || die "could not find pyproject.toml in $REPO_ROOT (is this the janito repo?)"
command -v uv >/dev/null 2>&1 || die "uv is required (see README_DEV.md); install it and re-run"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python interpreter '$PYTHON_BIN' not found on PATH"

# --- create the venv on first run -------------------------------------------
if [ ! -x "$VENV_PYTHON" ]; then
    say "Creating $VENV_DIR ..."
    uv venv --python "$(command -v "$PYTHON_BIN")" "$VENV_DIR"
fi

# --- build & install the current tree into the venv -------------------------
say "Building janito from $REPO_ROOT ..."
(
    cd "$REPO_ROOT"
    uv pip install --python "$VENV_PYTHON" .
)

# --- refresh the global launcher --------------------------------------------
mkdir -p "$BIN_DIR"
ln -sfn "$VENV_JANITO" "$BIN_LINK"

# --- report ------------------------------------------------------------------
say "Done."
"$BIN_LINK" --version
say "Run it with: $BIN_LINK"
