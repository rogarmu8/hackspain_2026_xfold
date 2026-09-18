# Source from the workspace root.
# Moon runs tasks in non-interactive bash, which does not load ~/.zshrc, so
# `pixi` is often missing even after a successful installer.

export PATH="${HOME}/.pixi/bin:/opt/homebrew/bin:/usr/local/bin:/usr/sbin:/usr/bin:/bin:${PATH:-}"

if ! command -v pixi >/dev/null 2>&1; then
  echo "pixi: command not found" >&2
  echo "Install Pixi (moon will find ~/.pixi/bin by itself after that):" >&2
  echo "  curl -fsSL https://pixi.sh/install.sh | sh" >&2
  echo "Or: brew install pixi" >&2
  exit 127
fi
