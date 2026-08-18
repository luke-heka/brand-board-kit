#!/usr/bin/env bash
# Brand Board installer. Idempotent: safe to run again to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Override the destination for a sandboxed test install.
DEST="${BRAND_BOARD_DEST:-${HOME}/.claude/skills/brand-board}"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
die() { printf '\n\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

say "Checking Python"
command -v python3 >/dev/null 2>&1 || die "Python 3.10+ is required. Install it from python.org, then run this again."
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "Python ${PYV} is too old. This needs 3.10 or newer."
echo "  Python ${PYV}"

say "Copying the skill to ${DEST}"
mkdir -p "${DEST}"
for item in SKILL.md engine templates docs assets scripts brands; do
  [ -e "${SRC}/${item}" ] || continue
  rm -rf "${DEST:?}/${item}"
  cp -R "${SRC}/${item}" "${DEST}/${item}"
done
# never clobber brands the user already made
echo "  copied"

say "Building the Python environment"
cd "${DEST}"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet playwright pypdf pillow
echo "  playwright, pypdf and pillow ready"

say "Downloading the render browser (about 150MB, once per machine)"
python3 -m playwright install chromium >/dev/null 2>&1 \
  || die "The browser download failed. Check your connection and run this again."
echo "  chromium ready"

say "Testing it"
if python3 -m engine.selftest; then
  :
else
  die "The engine's own tests did not pass. Run 'python3 -m engine.selftest' to see why."
fi

cat <<'DONE'

Installed.

Open Claude Code and say:

    Build a brand board for my business. The site is example.com.

Or do it by hand:

    cd ~/.claude/skills/brand-board
    source .venv/bin/activate
    cp -R brands/_starter brands/your-brand
    python3 -m engine.verify brands/your-brand

DONE
