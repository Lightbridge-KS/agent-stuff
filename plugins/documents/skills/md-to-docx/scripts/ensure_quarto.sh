#!/usr/bin/env bash
# Decide which render path this machine supports, installing Quarto if it can.
#
#   ./ensure_quarto.sh
#
# stdout: the render path to use — "quarto" or "pandoc" (branch on this)
# exit:   0 = quarto ready · 1 = quarto unavailable, pandoc fallback · 2 = neither
#
# On Linux without Quarto, attempts a user-local tarball install (no root) from GitHub
# releases into ~/.local — skipped quietly when there is no network (e.g. ChatGPT VMs).
# On macOS it does not install; use `brew install quarto` and re-run.

set -u

QUARTO_VERSION="${QUARTO_VERSION:-1.9.38}"

say() { echo "ensure_quarto: $*" >&2; }

if command -v quarto >/dev/null 2>&1; then
  say "quarto $(quarto --version 2>/dev/null) already on PATH"
  echo quarto
  exit 0
fi

if [ "$(uname -s)" = "Linux" ]; then
  case "$(uname -m)" in
    x86_64)          arch=amd64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *)               arch="" ;;
  esac
  if [ -n "$arch" ]; then
    url="https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${arch}.tar.gz"
    dest="$HOME/.local/share"
    bin="$HOME/.local/bin"
    say "attempting user-local install of quarto ${QUARTO_VERSION} (${arch})"
    mkdir -p "$dest" "$bin"
    if curl -fsSL --connect-timeout 10 --max-time 300 "$url" | tar -xz -C "$dest" 2>/dev/null; then
      ln -sf "$dest/quarto-${QUARTO_VERSION}/bin/quarto" "$bin/quarto"
      if "$bin/quarto" --version >/dev/null 2>&1; then
        say "installed to $bin/quarto — ensure $bin is on PATH"
        echo quarto
        exit 0
      fi
      say "downloaded but quarto does not run; falling back"
    else
      say "download failed (no network or blocked host); falling back"
    fi
  fi
else
  say "quarto not found; on macOS install with: brew install quarto"
fi

if command -v pandoc >/dev/null 2>&1; then
  say "using pandoc $(pandoc --version | head -1 | awk '{print $2}') fallback"
  echo pandoc
  exit 1
fi

say "neither quarto nor pandoc available — cannot render .docx on this machine"
exit 2
