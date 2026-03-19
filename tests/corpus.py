"""Feature test corpus: exercise all Flarecrawl features against real websites.

Runs every feature flag and format against a curated set of URLs designed
to cover edge cases: heavy JS, rich structured data, complex nav, images,
SPAs, long-form content, minimal pages.

Usage:
    python tests/corpus.py                    # Full corpus test
    python tests/corpus.py --feature schema   # Test one feature
    python tests/corpus.py --url-only         # List test URLs
    python tests/corpus.py --quick            # One URL per feature
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Test corpus: URLs chosen to exercise specific edge cases
# ---------------------------------------------------------------------------

CORPUS = [
    {
        "url": "https://example.com",
        "name": "minimal",
        "desc": "Minimal page — baseline, no images, no schema",
        "expect": {
            "main_content": "Example Domain",
            "images_min": 0,
            "schema_ld_json": 0,
            "schema_og": 0,
        },
    },
    {
        "url": "https://www.bbc.com",
        "name": "news-heavy",
        "desc": "News site — rich OG/Twitter/LD+JSON, many images, complex nav",
        "expect": {
            "main_content": None,  # dynamic
            "images_min": 5,
            "schema_ld_json": 1,
            "schema_og": 1,
        },
    },
    {
        "url": "https://docs.python.org/3/library/json.html",
        "name": "docs",
        "desc": "Documentation — deep nav, many headings, code blocks",
        "expect": {
            "main_content": "JSON encoder and decoder",
            "images_min": 0,
            "schema_ld_json": 0,
            "schema_og": 0,
        },
    },
    {
        "url": "https://en.wikipedia.org/wiki/Web_scraping",
        "name": "wiki",
        "desc": "Wikipedia — long content, many images, infobox, references",
        "expect": {
            "main_content": "Web scraping",
            "images_min": 2,
            "schema_ld_json": 0,
            "schema_og": 2,
        },
    },
    {
        "url": "https://github.com/trending",
        "name": "spa-heavy",
        "desc": "GitHub trending — dynamic JS, complex layout, many links",
        "expect": {
            "main_content": None,
            "images_min": 0,
            "schema_ld_json": 0,
            "schema_og": 2,
        },
    },
    {
        "url": "https://react.dev",
        "name": "spa",
        "desc": "React docs — SPA, client-side rendering, structured data",
        "expect": {
            "main_content": None,
            "images_min": 0,
            "schema_ld_json": 0,
            "schema_og": 2,
        },
    },
    {
        "url": "https://httpbin.org",
        "name": "api-docs",
        "desc": "API docs — Swagger UI, JS-rendered accordion",
        "expect": {
            "main_content": "HTTP",
            "images_min": 0,
            "schema_ld_json": 0,
            "schema_og": 0,
        },
    },
    {
        "url": "https://blog.cloudflare.com/workers-ai/",
        "name": "blog",
        "desc": "Blog post — article content, images, structured data",
        "expect": {
            "main_content": "Workers AI",
            "images_min": 1,
            "schema_ld_json": 0,
            "schema_og": 2,
        },
    },
]

# ---------------------------------------------------------------------------
# Features to test
# ---------------------------------------------------------------------------

FEATURES = [
    {
        "name": "scrape-default",
        "desc": "Basic markdown scrape",
        "cmd": ["flarecrawl", "scrape", "{url}", "--json", "--no-cache"],
        "check": lambda r, e: _check_content(r, min_len=50),
    },
    {
        "name": "only-main-content",
        "desc": "Main content extraction",
        "cmd": ["flarecrawl", "scrape", "{url}", "--only-main-content", "--json", "--no-cache"],
        "check": lambda r, e: _check_main_content(r, e),
    },
    {
        "name": "exclude-tags",
        "desc": "Exclude nav/footer",
        "cmd": ["flarecrawl", "scrape", "{url}", "--exclude-tags", "nav,footer,header",
                "--json", "--no-cache"],
        "check": lambda r, e: _check_content(r, min_len=20),
    },
    {
        "name": "format-images",
        "desc": "Image extraction",
        "cmd": ["flarecrawl", "scrape", "{url}", "--format", "images", "--json", "--no-cache"],
        "check": lambda r, e: _check_images(r, e),
    },
    {
        "name": "format-schema",
        "desc": "Structured data extraction",
        "cmd": ["flarecrawl", "scrape", "{url}", "--format", "schema", "--json", "--no-cache"],
        "check": lambda r, e: _check_schema(r, e),
    },
    {
        "name": "schema-command",
        "desc": "Schema command",
        "cmd": ["flarecrawl", "schema", "{url}", "--json", "--no-cache"],
        "check": lambda r, e: _check_schema_cmd(r, e),
    },
    {
        "name": "mobile",
        "desc": "Mobile viewport",
        "cmd": ["flarecrawl", "scrape", "{url}", "--mobile", "--json", "--no-cache"],
        "check": lambda r, e: _check_content(r, min_len=20),
    },
    {
        "name": "headers",
        "desc": "Custom headers",
        "cmd": ["flarecrawl", "scrape", "{url}", "--headers", "Accept-Language: en-US",
                "--json", "--no-cache"],
        "check": lambda r, e: _check_content(r, min_len=20),
    },
    {
        "name": "format-html",
        "desc": "HTML output",
        "cmd": ["flarecrawl", "scrape", "{url}", "--format", "html", "--json", "--no-cache"],
        "check": lambda r, e: _check_content(r, min_len=50, has="<"),
    },
    {
        "name": "diff",
        "desc": "Diff mode (first run)",
        "cmd": ["flarecrawl", "scrape", "{url}", "--diff", "--json", "--no-cache"],
        "check": lambda r, e: _check_diff(r),
    },
]

# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _parse_result(output: str) -> dict | None:
    """Parse JSON output from flarecrawl."""
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _check_content(result: dict, min_len: int = 50, has: str | None = None) -> tuple[bool, str]:
    """Check content exists and meets minimum length."""
    data = result.get("data", {})
    content = data.get("content", "")
    if isinstance(content, dict):
        content = json.dumps(content)
    if not content:
        return False, "empty content"
    if len(content) < min_len:
        return False, f"content too short ({len(content)} < {min_len})"
    if has and has not in content:
        return False, f"missing expected string: {has!r}"
    return True, f"ok ({len(content)} chars)"


def _check_main_content(result: dict, expect: dict) -> tuple[bool, str]:
    """Check main content extraction."""
    ok, msg = _check_content(result, min_len=20)
    if not ok:
        return ok, msg
    content = result.get("data", {}).get("content", "")
    expected = expect.get("main_content")
    if expected and expected not in content:
        return False, f"missing expected text: {expected!r}"
    return True, msg


def _check_images(result: dict, expect: dict) -> tuple[bool, str]:
    """Check image extraction results."""
    data = result.get("data", {})
    content = data.get("content", [])
    if not isinstance(content, list):
        return False, f"expected list, got {type(content).__name__}"
    min_images = expect.get("images_min", 0)
    if len(content) < min_images:
        return False, f"found {len(content)} images, expected >= {min_images}"
    # Validate image structure
    for img in content[:3]:
        if "url" not in img:
            return False, "image missing 'url' key"
    return True, f"ok ({len(content)} images)"


def _check_schema(result: dict, expect: dict) -> tuple[bool, str]:
    """Check structured data extraction from --format schema."""
    data = result.get("data", {})
    content = data.get("content", {})
    if not isinstance(content, dict):
        return False, f"expected dict, got {type(content).__name__}"
    ld = content.get("ld_json", [])
    og = content.get("opengraph", {})
    tc = content.get("twitter_card", {})
    min_ld = expect.get("schema_ld_json", 0)
    min_og = expect.get("schema_og", 0)
    issues = []
    if len(ld) < min_ld:
        issues.append(f"ld_json: {len(ld)} < {min_ld}")
    if len(og) < min_og:
        issues.append(f"opengraph: {len(og)} < {min_og}")
    if issues:
        return False, "; ".join(issues)
    return True, f"ok (ld:{len(ld)} og:{len(og)} tw:{len(tc)})"


def _check_schema_cmd(result: dict, expect: dict) -> tuple[bool, str]:
    """Check schema command output."""
    data = result.get("data", {})
    if not isinstance(data, dict):
        return False, f"expected dict, got {type(data).__name__}"
    ld = data.get("ld_json", [])
    og = data.get("opengraph", {})
    tc = data.get("twitter_card", {})
    return True, f"ok (ld:{len(ld)} og:{len(og)} tw:{len(tc)})"


def _check_diff(result: dict) -> tuple[bool, str]:
    """Check diff output exists."""
    data = result.get("data", {})
    if "diff" not in data:
        return False, "no diff key in result"
    diff = data["diff"]
    if not isinstance(diff, dict):
        return False, f"diff should be dict, got {type(diff).__name__}"
    return True, f"ok (added:{diff.get('added', '?')} removed:{diff.get('removed', '?')})"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    feature: str
    url_name: str
    url: str
    passed: bool
    message: str
    elapsed: float
    exit_code: int
    error: str = ""


def run_test(feature: dict, site: dict) -> TestResult:
    """Run a single feature test against a site."""
    url = site["url"]
    cmd = [c.replace("{url}", url) for c in feature["cmd"]]
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        elapsed = time.time() - start
        if proc.returncode != 0:
            error_msg = proc.stderr.strip() or proc.stdout.strip()
            # Try to parse JSON error
            try:
                err = json.loads(proc.stdout)
                error_msg = err.get("error", {}).get("message", error_msg)
            except (json.JSONDecodeError, AttributeError):
                pass
            return TestResult(
                feature=feature["name"], url_name=site["name"], url=url,
                passed=False, message=f"exit code {proc.returncode}",
                elapsed=elapsed, exit_code=proc.returncode, error=error_msg[:200],
            )

        result = _parse_result(proc.stdout)
        if result is None:
            return TestResult(
                feature=feature["name"], url_name=site["name"], url=url,
                passed=False, message="invalid JSON output",
                elapsed=elapsed, exit_code=0, error=proc.stdout[:200],
            )

        passed, message = feature["check"](result, site.get("expect", {}))
        return TestResult(
            feature=feature["name"], url_name=site["name"], url=url,
            passed=passed, message=message, elapsed=elapsed, exit_code=0,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            feature=feature["name"], url_name=site["name"], url=url,
            passed=False, message="timeout (60s)", elapsed=60.0, exit_code=-1,
        )
    except Exception as e:
        return TestResult(
            feature=feature["name"], url_name=site["name"], url=url,
            passed=False, message=str(e), elapsed=0, exit_code=-1,
        )


def main():
    parser = argparse.ArgumentParser(description="Flarecrawl feature test corpus")
    parser.add_argument("--feature", help="Test only this feature")
    parser.add_argument("--site", help="Test only this site (by name)")
    parser.add_argument("--url-only", action="store_true", help="List test URLs")
    parser.add_argument("--quick", action="store_true", help="One URL per feature")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    if args.url_only:
        for site in CORPUS:
            print(f"{site['name']:15s} {site['url']}")
            print(f"{'':15s} {site['desc']}")
        return

    # Filter
    features = FEATURES
    sites = CORPUS
    if args.feature:
        features = [f for f in FEATURES if f["name"] == args.feature]
        if not features:
            print(f"Unknown feature: {args.feature}")
            print("Available:", ", ".join(f["name"] for f in FEATURES))
            sys.exit(1)
    if args.site:
        sites = [s for s in CORPUS if s["name"] == args.site]
        if not sites:
            print(f"Unknown site: {args.site}")
            print("Available:", ", ".join(s["name"] for s in CORPUS))
            sys.exit(1)
    if args.quick:
        # Use example.com for most, bbc for schema/images
        quick_sites = {
            "scrape-default": "minimal",
            "only-main-content": "docs",
            "exclude-tags": "wiki",
            "format-images": "wiki",
            "format-schema": "news-heavy",
            "schema-command": "news-heavy",
            "mobile": "minimal",
            "headers": "minimal",
            "format-html": "minimal",
            "diff": "minimal",
        }
        filtered = []
        for f in features:
            site_name = quick_sites.get(f["name"], "minimal")
            site = next((s for s in CORPUS if s["name"] == site_name), CORPUS[0])
            filtered.append((f, site))
    else:
        filtered = [(f, s) for f in features for s in sites]

    # Run
    results: list[TestResult] = []
    total = len(filtered)
    print(f"\nRunning {total} tests ({len(features)} features x {len(sites) if not args.quick else 1} sites)\n")
    print(f"{'#':>3s}  {'Feature':20s} {'Site':15s} {'Result':6s} {'Time':>6s}  Message")
    print("-" * 80)

    for i, (feat, site) in enumerate(filtered, 1):
        if args.quick:
            pass
        print(f"{i:3d}  {feat['name']:20s} {site['name']:15s} ", end="", flush=True)
        result = run_test(feat, site)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        color = "" if result.passed else ""
        print(f"{status:6s} {result.elapsed:5.1f}s  {result.message}")
        if not result.passed and result.error:
            print(f"     {'':20s} {'':15s}        error: {result.error[:80]}")

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print("-" * 80)
    print(f"\nResults: {passed} passed, {failed} failed, {total} total")

    if failed:
        print(f"\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  {r.feature:20s} {r.url_name:15s} {r.message}")

    # Save
    if args.output:
        output_data = [
            {
                "feature": r.feature, "site": r.url_name, "url": r.url,
                "passed": r.passed, "message": r.message, "elapsed": r.elapsed,
                "exit_code": r.exit_code, "error": r.error,
            }
            for r in results
        ]
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {args.output}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
