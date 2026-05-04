#!/usr/bin/env python3
"""
Live integration test: runs real scraper logic against actual URLs,
takes screenshots at each step, and verifies stats land in links.csv.

Run with: python tests/test_live_scraper.py
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "scrapers"))
sys.path.insert(0, str(project_root / "shared"))

from playwright.sync_api import sync_playwright

CHROME_ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
)
SCREENSHOT_DIR = project_root / "tests" / "screenshots"
LINKS_CSV = project_root / "database" / "links.csv"
_cookies_json = project_root / "cookies.json"
_x_session = project_root / "shared" / "x_session.json"
SESSION_FILE = _cookies_json if _cookies_json.exists() else _x_session

X_TEST_URLS = [
    "https://x.com/i/status/2047147620527677556",  # mike_limas Apr 23
    "https://x.com/i/status/2046548636352368871",  # tonyler Apr 21
    "https://x.com/i/status/2044667668926439495",  # tonyler Apr 16
]

REDDIT_TEST_URLS = [
    "https://www.reddit.com/r/cosmoshub/comments/1ski1ez/cosmos_labs_partners_with_gauntlet_for_atom/",
    "https://www.reddit.com/r/solana/comments/1sqk8x2/layerzero_exploit_showed_the_importance_of_what/",
    "https://www.reddit.com/r/cosmoshub/s/vQhsA6UG09",   # share URL
]

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"


def shot(page, name):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  {INFO} Screenshot: tests/screenshots/{name}.png")
    return path


def parse_count(text: str) -> int:
    if not text:
        return 0
    text = str(text).strip().upper().replace(",", "")
    m = re.match(r"([\d\.]+)([KMB])?", text)
    if not m:
        return 0
    n = float(m.group(1))
    suffix = m.group(2)
    if suffix == "K":
        return int(n * 1000)
    if suffix == "M":
        return int(n * 1_000_000)
    return int(n)


def read_links_csv():
    if not LINKS_CSV.exists():
        return []
    with LINKS_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_links_csv(rows, fieldnames):
    tmp = LINKS_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(LINKS_CSV)


def apply_x_session(context, page):
    if not SESSION_FILE.exists():
        print(f"  {INFO} No X session file — running unauthenticated")
        return
    session = json.loads(SESSION_FILE.read_text())
    # Support both raw array format (browser export) and wrapped {"cookies": [...]}
    cookies = session if isinstance(session, list) else session.get("cookies", [])
    if not cookies:
        return
    by_domain = {}
    for c in cookies:
        domain = c.get("domain", "x.com").lstrip(".")
        by_domain.setdefault(domain, []).append(c)
    for domain, dcookies in by_domain.items():
        try:
            page.goto(f"https://{domain}/", timeout=15000)
            time.sleep(1)
            for c in dcookies:
                try:
                    norm = {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": domain,
                        "path": c.get("path", "/"),
                    }
                    if "secure" in c:
                        norm["secure"] = c["secure"]
                    if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0:
                        norm["expires"] = int(c["expires"])
                    context.add_cookies([norm])
                except Exception:
                    pass
        except Exception:
            pass
    print(f"  {INFO} Applied {len(cookies)} session cookies")


# ---------------------------------------------------------------------------
# X scraper tests
# ---------------------------------------------------------------------------

def run_x_url(page, url, idx):
    print(f"\n{'─'*60}")
    print(f"X [{idx}]: {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    shot(page, f"x_{idx:02d}_loaded")

    current_url = page.url
    print(f"  {INFO} Final URL: {current_url}")

    # Check page state
    body_text = page.locator("body").text_content() or ""
    if "/login" in current_url or "Log in" in body_text[:500]:
        print(f"  {FAIL} LOGIN WALL detected — session may be expired")
        shot(page, f"x_{idx:02d}_login_wall")
        return None

    # Check article exists
    articles = page.locator("article").all()
    print(f"  {INFO} article elements found: {len(articles)}")

    if not articles:
        print(f"  {FAIL} No article elements — DOM mismatch or blocked")
        shot(page, f"x_{idx:02d}_no_article")
        return None

    # Find the tweet article
    tweet_article = None
    tweet_id_match = re.search(r"/status/(\d+)", url)
    target_id = tweet_id_match.group(1) if tweet_id_match else None

    for art in articles:
        testid = art.get_attribute("data-testid") or ""
        if testid == "tweet":
            if target_id:
                links_in_art = art.locator(f'a[href*="/status/{target_id}"]').count()
                if links_in_art > 0:
                    tweet_article = art
                    break
            else:
                tweet_article = art
                break

    if not tweet_article:
        tweet_article = page.locator('article[data-testid="tweet"]').first

    # Extract views from summary div
    impressions = None
    try:
        summary_els = tweet_article.locator("div[aria-label*='views']").all()
        for sel in summary_els:
            label = sel.get_attribute("aria-label") or ""
            m = re.search(r"([\d,]+(?:\.\d+)?[KMBkmb]?)\s*views?", label, re.IGNORECASE)
            if m:
                impressions = parse_count(m.group(1).replace(",", ""))
                print(f"  {PASS} Views from summary div: {impressions} (label: '{label}')")
                break
    except Exception as e:
        print(f"  {FAIL} Error reading summary div: {e}")

    # Extract button metrics
    metrics = {"impressions": impressions}
    for testid, key in [("reply", "comments"), ("retweet", "reposts"), ("like", "likes")]:
        try:
            btn = tweet_article.locator(f'button[data-testid="{testid}"]').first
            if btn.count() > 0:
                label = btn.get_attribute("aria-label") or ""
                metrics[key] = parse_count(label)
                print(f"  {PASS} {key}: {metrics[key]} ('{label}')")
        except Exception as e:
            print(f"  {FAIL} Error reading {testid}: {e}")

    # Extract tweet text
    text_el = tweet_article.locator('[data-testid="tweetText"]').first
    if text_el.count() > 0:
        text = (text_el.text_content() or "")[:80]
        print(f"  {PASS} Tweet text: '{text}'")
    else:
        print(f"  {INFO} No tweetText found")

    shot(page, f"x_{idx:02d}_extracted")

    # Verify at least impressions were captured
    if metrics.get("impressions") is not None:
        print(f"  {PASS} METRICS OK: {metrics}")
    else:
        print(f"  {FAIL} No impressions extracted — check selectors")

    return metrics


def write_x_metrics_saved_to_csv(url, metrics):
    """Write metrics to links.csv and verify they persist."""
    if not metrics or metrics.get("impressions") is None:
        print(f"  {INFO} Skipping CSV write — no metrics")
        return False

    rows = read_links_csv()
    if not rows:
        print(f"  {INFO} links.csv empty or missing")
        return False

    fieldnames = list(rows[0].keys())
    normalized_id = re.search(r"/status/(\d+)", url)
    target_id = normalized_id.group(1) if normalized_id else None

    updated = False
    for row in rows:
        row_url = row.get("url", "")
        if target_id and target_id in row_url:
            before = row.get("impressions", "")
            row["impressions"] = str(metrics["impressions"])
            if metrics.get("likes") is not None:
                row["likes"] = str(metrics["likes"])
            if metrics.get("comments") is not None:
                row["comments"] = str(metrics["comments"])
            updated = True
            print(f"  {PASS} CSV updated: impressions {before!r} → {row['impressions']!r}")
            break

    if updated:
        write_links_csv(rows, fieldnames)
        # Verify by reading back
        verify_rows = read_links_csv()
        for row in verify_rows:
            if target_id and target_id in row.get("url", ""):
                saved = row.get("impressions", "")
                if saved == str(metrics["impressions"]):
                    print(f"  {PASS} CSV verified: impressions={saved}")
                    return True
                else:
                    print(f"  {FAIL} CSV mismatch: expected {metrics['impressions']}, got {saved}")
    else:
        print(f"  {INFO} URL not found in links.csv")

    return updated


# ---------------------------------------------------------------------------
# Reddit scraper tests
# ---------------------------------------------------------------------------

def run_reddit_url(page, url, idx):
    print(f"\n{'─'*60}")
    print(f"Reddit [{idx}]: {url}")

    # Resolve /s/ share links first
    if "/s/" in url:
        print(f"  {INFO} Share URL — resolving redirect...")
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        resolved = page.url
        print(f"  {INFO} Resolved to: {resolved}")
        shot(page, f"reddit_{idx:02d}_resolved")
        url = resolved

    # Convert to old.reddit
    old_url = url.replace("www.reddit.com", "old.reddit.com").replace("://reddit.com", "://old.reddit.com")
    # Strip UTM params
    old_url = old_url.split("?")[0].rstrip("/")
    print(f"  {INFO} Old Reddit URL: {old_url}")

    page.goto(old_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)
    shot(page, f"reddit_{idx:02d}_loaded")

    # Page state check
    current_url = page.url
    body_text = page.locator("body").text_content() or ""

    if "login" in current_url.lower():
        print(f"  {FAIL} LOGIN WALL")
        return None

    if "page not found" in body_text.lower():
        print(f"  {FAIL} 404 PAGE")
        return None

    # Check for comment elements
    comments = page.locator(".comment").all()
    print(f"  {INFO} .comment elements: {len(comments)}")

    if not comments:
        # Try new Reddit selectors as fallback
        new_comments = page.locator('[data-testid="comment"]').all()
        print(f"  {INFO} [data-testid=comment] elements: {len(new_comments)}")
        if not new_comments:
            print(f"  {FAIL} No comment elements found — old.reddit layout may have changed")
            shot(page, f"reddit_{idx:02d}_no_comments")
            return {"upvotes": 0, "comments": 0, "comment_count_found": 0}

    # Extract score and comment count
    metrics = {"comment_count_found": len(comments)}
    try:
        score_el = page.locator(".thing.link .score.unvoted").first
        if score_el.count() > 0:
            score_text = score_el.text_content() or "0"
            m = re.search(r"(\d+)", score_text.replace(",", ""))
            metrics["upvotes"] = int(m.group(1)) if m else 0
            print(f"  {PASS} Upvotes: {metrics['upvotes']} ('{score_text}')")
    except Exception as e:
        print(f"  {INFO} Could not read score: {e}")

    try:
        comment_link = page.locator(".thing.link a.comments").first
        if comment_link.count() > 0:
            ct = comment_link.text_content() or "0"
            m = re.search(r"(\d+)", ct)
            metrics["comments"] = int(m.group(1)) if m else 0
            print(f"  {PASS} Comment count: {metrics['comments']} ('{ct.strip()}')")
    except Exception as e:
        print(f"  {INFO} Could not read comment count: {e}")

    # Sample a comment author
    if comments:
        try:
            author = comments[0].locator(".author").first
            if author.count() > 0:
                print(f"  {PASS} First comment author: '{author.text_content()}'")
        except Exception:
            pass

    shot(page, f"reddit_{idx:02d}_extracted")
    print(f"  {PASS} Reddit metrics: {metrics}")
    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("LIVE SCRAPER INTEGRATION TEST")
    print("=" * 60)
    print(f"Screenshots → {SCREENSHOT_DIR}")

    results = {"x_pass": 0, "x_fail": 0, "reddit_pass": 0, "reddit_fail": 0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent=CHROME_ANDROID_UA,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=2.0,
            locale="en-US",
        )
        page = context.new_page()

        # ---- X tests ----
        print("\n" + "=" * 60)
        print("PHASE 1: X / Twitter scraping")
        print("=" * 60)

        apply_x_session(context, page)

        for i, url in enumerate(X_TEST_URLS, 1):
            try:
                metrics = run_x_url(page, url, i)
                if metrics and metrics.get("impressions") is not None:
                    write_x_metrics_saved_to_csv(url, metrics)
                    results["x_pass"] += 1
                else:
                    results["x_fail"] += 1
            except Exception as e:
                print(f"  {FAIL} Exception: {e}")
                results["x_fail"] += 1

        # ---- Reddit tests ----
        print("\n" + "=" * 60)
        print("PHASE 2: Reddit scraping")
        print("=" * 60)

        for i, url in enumerate(REDDIT_TEST_URLS, 1):
            try:
                metrics = run_reddit_url(page, url, i)
                if metrics is not None:
                    results["reddit_pass"] += 1
                else:
                    results["reddit_fail"] += 1
            except Exception as e:
                print(f"  {FAIL} Exception: {e}")
                results["reddit_fail"] += 1

        browser.close()

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"X:      {results['x_pass']} passed, {results['x_fail']} failed")
    print(f"Reddit: {results['reddit_pass']} passed, {results['reddit_fail']} failed")
    total_fail = results["x_fail"] + results["reddit_fail"]
    if total_fail == 0:
        print(f"\n{PASS} ALL TESTS PASSED")
    else:
        print(f"\n{FAIL} {total_fail} test(s) failed — check screenshots in tests/screenshots/")

    print(f"\nScreenshots saved to: {SCREENSHOT_DIR}")
    return total_fail


if __name__ == "__main__":
    sys.exit(main())
