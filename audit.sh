#!/usr/bin/env bash
# Audits the downloaded static site for:
#   - Remaining archive.org references (links that were not rewritten)
#   - Referenced local assets that are missing on disk
#   - Redirects that were not followed (30x pages)
# Run from the repo root after download.sh completes.

set -euo pipefail

SITE_DIR="$(pwd)/websites/bartonhistory.wikispaces.com"
REPORT="$(pwd)/audit-report.txt"

if [[ ! -d "$SITE_DIR" ]]; then
  echo "ERROR: $SITE_DIR not found. Run download.sh first."
  exit 1
fi

echo "Auditing $SITE_DIR ..." | tee "$REPORT"
echo "Generated: $(date -u)" | tee -a "$REPORT"
echo "" | tee -a "$REPORT"

# ── 1. Archive.org references still present ────────────────────────────────────
echo "## 1. Remaining archive.org references" | tee -a "$REPORT"
ARCHIVEORG_REFS=$(grep -rn --include="*.html" --include="*.css" --include="*.js" \
  "archive\.org" "$SITE_DIR" 2>/dev/null | \
  grep -v "<!--" | \
  grep -v "Wayback Machine" || true)

if [[ -z "$ARCHIVEORG_REFS" ]]; then
  echo "   None found — all links successfully rewritten." | tee -a "$REPORT"
else
  echo "$ARCHIVEORG_REFS" | tee -a "$REPORT"
fi
echo "" | tee -a "$REPORT"

# ── 2. Missing local assets referenced in HTML ─────────────────────────────────
echo "## 2. Missing local assets" | tee -a "$REPORT"
MISSING=()
while IFS= read -r html_file; do
  # Extract src= and href= values that look like local paths
  while IFS= read -r ref; do
    # Strip leading ./ or /
    clean="${ref#./}"
    clean="${clean#/}"
    # Skip empty, anchors, mailto, javascript, external http
    [[ -z "$clean" ]] && continue
    [[ "$clean" == \#* ]] && continue
    [[ "$clean" == mailto* ]] && continue
    [[ "$clean" == javascript* ]] && continue
    [[ "$clean" == http* ]] && continue

    candidate="$SITE_DIR/$clean"
    if [[ ! -f "$candidate" ]]; then
      MISSING+=("MISSING  $clean  (referenced in ${html_file#$SITE_DIR/})")
    fi
  done < <(grep -oP '(?:href|src|action)=["'"'"']\K[^"'"'"']+' "$html_file" 2>/dev/null | \
           grep -v "^http" | grep -v "^#" | grep -v "^mailto" | grep -v "^javascript" || true)
done < <(find "$SITE_DIR" -name "*.html" -type f)

if [[ ${#MISSING[@]} -eq 0 ]]; then
  echo "   No missing local assets detected." | tee -a "$REPORT"
else
  printf '%s\n' "${MISSING[@]}" | sort -u | tee -a "$REPORT"
fi
echo "" | tee -a "$REPORT"

# ── 3. Pages that are redirect stubs (30x) ────────────────────────────────────
echo "## 3. Redirect stubs (pages that are 30x responses)" | tee -a "$REPORT"
REDIRECTS=$(grep -rl --include="*.html" \
  -e "This page has moved" \
  -e "301 Moved" -e "302 Found" -e "307 Temporary" \
  "$SITE_DIR" 2>/dev/null || true)

if [[ -z "$REDIRECTS" ]]; then
  echo "   None found." | tee -a "$REPORT"
else
  echo "$REDIRECTS" | sed "s|$SITE_DIR/||" | tee -a "$REPORT"
fi
echo "" | tee -a "$REPORT"

# ── 4. File-type summary ───────────────────────────────────────────────────────
echo "## 4. Downloaded file summary" | tee -a "$REPORT"
find "$SITE_DIR" -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | \
  awk '{printf "   %5d  .%s\n", $1, $2}' | tee -a "$REPORT"
echo "" | tee -a "$REPORT"

TOTAL=$(find "$SITE_DIR" -type f | wc -l)
echo "   Total files: $TOTAL" | tee -a "$REPORT"

echo ""
echo "Audit complete. Full report: $REPORT"
