#!/usr/bin/env python3
"""
rewrite_links.py

Two-phase post-processing tool for the downloaded Wikispaces backup:

  Phase 1 – rename %2A-prefixed directories to *-prefixed ones.
    The wayback-machine-downloader saves pages whose URL starts with %2A
    (encoded '*') using the literal string "%2A" as part of the directory
    name, e.g. "%2ABernard+Barton.../index.html".  Web servers decode %2A
    to '*' before looking up the file, so the server looks for "*Bernard..."
    and gets a 404.  Renaming to "*..." fixes this permanently.

  Phase 2 – rewrite Wayback Machine wrapper URLs in every HTML attribute.
    href/src/action values of the form
      ./web/20150512110327cs_/http://bartonhistory.wikispaces.com/People
    become proper relative paths:
      ../People/index.html   (resolved from the current file's location)
    Values wrapping other domains become plain absolute HTTPS links:
      ./web/20150512110327js_/http://www.wikispaces.com/s/main.js
      → https://www.wikispaces.com/s/main.js

Only href, src, and action attributes are rewritten; script/style block
content is left alone (those are dead wikispaces editor/tracking URLs).

The script is idempotent — running it twice produces the same result.

Usage:
  python rewrite_links.py [site_dir]

  site_dir defaults to  websites/bartonhistory.wikispaces.com
"""

import os
import re
import sys
import urllib.parse
from pathlib import Path

# ── configuration ────────────────────────────────────────────────────────────

SITE_DOMAIN = "bartonhistory.wikispaces.com"
DEFAULT_SITE = Path("websites/bartonhistory.wikispaces.com")

# ── regex patterns ────────────────────────────────────────────────────────────

# Matches a Wayback Machine URL wrapping an http/https target.
# Captures (1) domain, (2) everything after the domain (path / query / fragment).
WAYBACK_RE = re.compile(
    r"^\./web/\d+[^/]*/https?://([^/?#\"'\s]+)(.*)?$",
    re.IGNORECASE | re.DOTALL,
)

# Matches a Wayback Machine URL wrapping a non-http scheme (e.g. mailto:, ftp:).
# Captures (1) the full original URL from the scheme onward.
WAYBACK_SCHEME_RE = re.compile(
    r"^\./web/\d+[^/]*/((?:mailto|ftp|tel):[^\"'\s]*)$",
    re.IGNORECASE,
)

# Matches   href="..."   src='...'   action="..."
# Two alternatives for double- vs single-quoted values.
ATTR_RE = re.compile(
    r"""((?:href|src|action)=")([^"]*)(")"""
    r"""|"""
    r"""((?:href|src|action)=')([^']*)(')""",
    re.IGNORECASE,
)


# ── phase 1: rename %2A directories ──────────────────────────────────────────

def rename_percent2a(site_dir: Path) -> int:
    """
    Rename any path component literally named '%2A...' to '*...' so that
    web servers can find the file when the URL contains %2A (which they
    decode to '*' before the filesystem lookup).

    Works bottom-up (deepest paths first) to avoid renaming a parent before
    its children have been moved.

    Returns the number of items renamed.
    """
    # Collect everything that has %2A in any component, deepest first
    victims = sorted(
        (p for p in site_dir.rglob("*") if "%2A" in p.name),
        key=lambda p: len(p.parts),
        reverse=True,
    )

    count = 0
    for path in victims:
        new_path = path.parent / path.name.replace("%2A", "*")
        if not new_path.exists():
            path.rename(new_path)
            count += 1

    return count


# ── phase 2: rewrite HTML links ───────────────────────────────────────────────

def find_icase(base: Path, name: str) -> Path | None:
    """
    Return base/name if it exists exactly, or a case-insensitive match if
    the filesystem is case-sensitive and only a differently-cased entry exists.
    Returns None if no match is found.
    """
    exact = base / name
    if exact.exists():
        return exact
    if not base.is_dir():
        return None
    lower = name.lower()
    for child in base.iterdir():
        if child.name.lower() == lower:
            return child
    return None


def url_path_to_local(url_path: str, site_dir: Path) -> Path:
    """
    Map the path portion of a bartonhistory.wikispaces.com URL to the best
    available local file.  Checks in order:

      1. PATH/index.html   – directory-style page (most content pages)
      2. PATH.html         – extension-less file that was copied to .html
      3. PATH              – extension-less file as saved by the downloader
      4. PATH/index.html   – fallback for pages not yet downloaded

    Each lookup uses case-insensitive matching so that, e.g., the URL path
    "home" resolves to the on-disk directory "Home/".
    """
    # Standard URL decode: %2A → '*', %28 → '(', '+' stays '+', etc.
    decoded = urllib.parse.unquote(url_path).lstrip("/")

    if not decoded:
        return site_dir / "index.html"

    # Resolve each path component case-insensitively against the real filesystem
    resolved = site_dir
    for component in decoded.split("/"):
        match = find_icase(resolved, component)
        resolved = match if match else (resolved / component)

    # resolved now points to either the directory or a file (if it was a flat URL)
    if resolved.is_dir():
        idx = resolved / "index.html"
        return idx                              # may or may not exist yet

    as_html = Path(str(resolved) + ".html")
    if as_html.exists():
        return as_html
    if resolved.exists():
        return resolved
    # Not yet downloaded — assume it will be a directory-style page
    return resolved / "index.html"


def make_relative(url_rest: str, current_file: Path, site_dir: Path) -> str:
    """
    Convert the path portion of a bartonhistory URL to a path relative to
    current_file.  Preserves fragments; discards query strings (Wikispaces
    dynamic-UI params with no local equivalent).
    """
    fragment = ""
    path_str = url_rest

    if "#" in path_str:
        path_str, frag = path_str.split("#", 1)
        fragment = "#" + frag

    if "?" in path_str:
        path_str = path_str.split("?")[0]

    target = url_path_to_local(path_str, site_dir)
    rel = os.path.relpath(target, current_file.parent).replace("\\", "/")
    if not rel.startswith("."):
        rel = "./" + rel
    return rel + fragment


def rewrite_url(url: str, current_file: Path, site_dir: Path) -> str:
    # Non-http schemes wrapped in a wayback URL (mailto:, ftp:, tel:, …)
    ms = WAYBACK_SCHEME_RE.match(url)
    if ms:
        return ms.group(1)

    m = WAYBACK_RE.match(url)
    if not m:
        return url

    domain = m.group(1).lower().rstrip("/")
    rest   = m.group(2) or ""

    if domain in (SITE_DOMAIN, "www." + SITE_DOMAIN):
        return make_relative(rest, current_file, site_dir)
    else:
        return f"https://{domain}{rest}"


def fix_relative_case(url: str, current_file: Path, site_dir: Path) -> str:
    """
    For an already-relative URL (written by the downloader's --local pass)
    that resolves to a non-existent path, try to find the correct casing on
    disk and return the fixed URL.  Returns url unchanged if no fix is needed
    or no case-insensitive match exists.
    """
    # Only handle ./... and ../... paths; skip anchors, external, and infra.
    if not (url.startswith("./") or url.startswith("../")):
        return url
    if url.startswith("http") or "web.archive.org" in url:
        return url

    fragment = ""
    path_part = url
    if "#" in path_part:
        path_part, frag = path_part.split("#", 1)
        fragment = "#" + frag

    # Resolve the relative path against the current file's directory
    abs_target = (current_file.parent / path_part).resolve()

    if abs_target.exists():
        return url  # already correct

    # Try to find the path by walking case-insensitively from site_dir
    try:
        rel_to_site = abs_target.relative_to(site_dir.resolve())
    except ValueError:
        return url  # outside site_dir, leave unchanged

    resolved = site_dir.resolve()
    for component in rel_to_site.parts:
        match = find_icase(resolved, component)
        if match:
            resolved = match
        else:
            return url  # component not found even case-insensitively

    # Build the corrected relative path from the current file
    fixed_rel = os.path.relpath(resolved, current_file.parent).replace("\\", "/")
    if not fixed_rel.startswith("."):
        fixed_rel = "./" + fixed_rel
    return fixed_rel + fragment


def rewrite_file(html_path: Path, site_dir: Path) -> int:
    text = html_path.read_text(encoding="utf-8", errors="replace")
    changes = 0

    def replace_attr(m: re.Match) -> str:
        nonlocal changes
        if m.group(1) is not None:
            prefix, url, suffix = m.group(1), m.group(2), m.group(3)
        else:
            prefix, url, suffix = m.group(4), m.group(5), m.group(6)

        # First try to rewrite wayback-wrapped URLs
        new_url = rewrite_url(url, html_path, site_dir)
        # Then fix case issues in already-relative links the downloader wrote
        if new_url == url:
            new_url = fix_relative_case(url, html_path, site_dir)

        if new_url != url:
            changes += 1
        return prefix + new_url + suffix

    new_text = ATTR_RE.sub(replace_attr, text)
    if new_text != text:
        html_path.write_text(new_text, encoding="utf-8", errors="replace")
    return changes


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    site_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SITE

    if not site_dir.is_dir():
        sys.exit(f"ERROR: directory not found: {site_dir}")

    # Phase 1: rename %2A directories
    renamed = rename_percent2a(site_dir)
    if renamed:
        print(f"Renamed {renamed} %2A-prefixed path(s) to *-prefixed.")
    else:
        print("No %2A-prefixed paths found (already renamed or none present).")

    # Phase 2: rewrite HTML attribute URLs
    html_files = sorted(site_dir.rglob("*.html"))
    print(f"Scanning {len(html_files)} HTML files in {site_dir} ...")

    total_links = 0
    total_files = 0

    for f in html_files:
        n = rewrite_file(f, site_dir)
        if n:
            print(f"  {f.relative_to(site_dir)}: {n} links rewritten")
            total_links += n
            total_files += 1

    print(f"\nDone — {total_links} links rewritten across {total_files} files.")


if __name__ == "__main__":
    main()
