#!/usr/bin/env bash
# Downloads bartonhistory.wikispaces.com from the Wayback Machine using
# https://github.com/StrawberryMaster/wayback-machine-downloader
# Run this from the repo root on your local machine.

set -euo pipefail

TOOL_DIR="/tmp/wayback-machine-downloader"
# No trailing slash — the tool checks for '/' after stripping the scheme to
# decide if a path was given. A trailing slash tricks it into skipping the
# '/*' wildcard it appends for host-only URLs, so only the homepage is queried.
TARGET_URL="http://bartonhistory.wikispaces.com/*"
OUTPUT_DIR="$(pwd)/websites/bartonhistory.wikispaces.com"
# Broad window: grab the best available snapshot of each URL up to end-2015.
# Wikispaces pages were often first crawled months before or after a given date,
# so a narrow window around May 2015 misses most of the site.
FROM_TS=20100101000000
TO_TS=20151231235959
# Concurrency: keep low to avoid archive.org rate-limiting.
CONCURRENCY=3

# ── 1. Ensure the tool is available ────────────────────────────────────────────
if ! command -v ruby &>/dev/null; then
  echo "ERROR: Ruby is required. Install it with your package manager."
  exit 1
fi

if [[ ! -f "$TOOL_DIR/bin/wayback_machine_downloader" ]]; then
  echo "Cloning wayback-machine-downloader..."
  git clone https://github.com/StrawberryMaster/wayback-machine-downloader "$TOOL_DIR"
  # Patch the Ruby version requirement if needed (the gem requires >= 3.4.3)
  sed -i 's/required_ruby_version = ">= 3.4.3"/required_ruby_version = ">= 3.3.0"/' \
    "$TOOL_DIR/wayback_machine_downloader.gemspec" 2>/dev/null || true
fi

# Install the runtime dependency if missing.
if ! ruby -e "require 'concurrent-ruby'" 2>/dev/null; then
  echo "Installing concurrent-ruby gem..."
  gem install concurrent-ruby
fi

WMD="ruby $TOOL_DIR/bin/wayback_machine_downloader"

# ── 2. Download ─────────────────────────────────────────────────────────────────
echo "==> Starting download of $TARGET_URL"
echo "    Output: $OUTPUT_DIR"
echo "    Timestamp window: $FROM_TS – $TO_TS"
echo "    Concurrency: $CONCURRENCY"
echo ""

mkdir -p "$OUTPUT_DIR"

$WMD \
  --directory "$OUTPUT_DIR" \
  --from "$FROM_TS" \
  --to   "$TO_TS" \
  --rewritten \
  --local \
  --page-requisites \
  --concurrency "$CONCURRENCY" \
  --retry 5 \
  "$TARGET_URL" \
  2>&1 | tee "$OUTPUT_DIR/../download.log"

echo ""
echo "==> Download complete. Log saved to $OUTPUT_DIR/../download.log"
echo "    Run ./audit.sh next to check for missing assets."
