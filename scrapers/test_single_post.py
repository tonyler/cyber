#!/usr/bin/env python3
"""Quick test to scrape a single X post and extract content."""

import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_scrape_post(url: str, headless: bool = False):
    """Test scraping a single X post."""

    # Normalize URL
    match = re.search(r"/status(?:es)?/(\d+)", url)
    if match:
        url = f"https://x.com/i/status/{match.group(1)}"

    print(f"Testing URL: {url}")
    print("=" * 60)

    playwright = sync_playwright().start()

    try:
        browser = playwright.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )

        # Use iPhone 14 Pro device profile (mobile X - simpler DOM)
        iphone = playwright.devices['iPhone 14 Pro']
        context = browser.new_context(
            **iphone,
            ignore_https_errors=True,
            locale='en-US'
        )

        # Load session cookies if available
        session_path = Path(__file__).parent.parent / "shared" / "x_session.json"
        if session_path.exists():
            print(f"Loading session from: {session_path}")
            with session_path.open('r') as f:
                session_data = json.load(f)

            cookies = session_data.get('cookies', [])
            page = context.new_page()

            # Apply cookies per domain
            cookies_by_domain = {}
            for cookie in cookies:
                domain = cookie.get('domain', 'x.com').lstrip('.')
                cookies_by_domain.setdefault(domain, []).append(cookie)

            for domain, domain_cookies in cookies_by_domain.items():
                try:
                    page.goto(f"https://{domain}/")
                    time.sleep(1)

                    for cookie in domain_cookies:
                        normalized = {
                            'name': cookie.get('name'),
                            'value': cookie.get('value'),
                            'domain': domain,
                            'path': cookie.get('path', '/'),
                        }
                        if 'secure' in cookie:
                            normalized['secure'] = cookie['secure']
                        if 'httpOnly' in cookie:
                            normalized['httpOnly'] = cookie['httpOnly']
                        expires = cookie.get('expires')
                        if isinstance(expires, (int, float)) and expires > 0:
                            normalized['expires'] = int(expires)

                        if normalized['name'] and normalized['value'] is not None:
                            try:
                                context.add_cookies([normalized])
                            except Exception:
                                pass
                except Exception as e:
                    print(f"Warning: Failed to apply cookies for {domain}: {e}")

            print(f"Applied {len(cookies)} session cookies")
        else:
            print("No session file found - scraping without login")
            page = context.new_page()

        # Navigate to the tweet
        print(f"\nNavigating to: {url}")
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        time.sleep(4)

        # Check for login wall or error
        page_content = page.content()
        current_url = page.url
        print(f"Current URL: {current_url}")

        # Extract data
        results = {
            'url': url,
            'content': None,
            'username': None,
            'timestamp': None,
            'metrics': {}
        }

        # Find main tweet article
        tweet_article = page.locator('article').first

        if tweet_article.count() == 0:
            print("\nERROR: No tweet article found!")
            print("Page might be blocked or login required")

            # Check for common error states
            if 'login' in current_url.lower() or 'signin' in current_url.lower():
                print("-> Redirected to login page")
            elif 'Something went wrong' in page_content:
                print("-> X returned error page")
            else:
                print("-> Unknown error state")

            return results

        print("\nTweet article found!")

        # Extract tweet text - check for article first
        # X articles have data-testid="twitterArticleReadView"
        article_view = tweet_article.locator('[data-testid="twitterArticleReadView"]').first
        is_article = article_view.count() > 0

        if is_article:
            # Get full text content from article view
            article_text = article_view.text_content() or ""

            # The article text starts with the title, followed by metrics numbers
            # Title ends where numbers begin (e.g., "15822335110K" = metrics)
            # Match where metrics start - typically a sequence of numbers
            title_match = re.match(r'^(.+?)(?:\s*\d+[KMB]?\s*\d+[KMB]?\s*\d+[KMB]?\s*\d+[KMB]?|$)', article_text)
            if title_match:
                article_title = title_match.group(1).strip()
            else:
                # Fallback: take first 200 chars and cut at sentence end
                article_title = article_text[:200].rsplit('.', 1)[0] if '.' in article_text[:200] else article_text[:100]

            if article_title:
                results['content'] = f"[Article] {article_title}"
                results['is_article'] = True
                print(f"\n--- ARTICLE TITLE ---")
                print(article_title)
                print("--- END TITLE ---")

        # Regular tweet text (if not an article or article title not found)
        if not is_article or not results.get('content'):
            text_element = tweet_article.locator('[data-testid="tweetText"]').first
            if text_element.count() > 0:
                results['content'] = text_element.text_content()
                print(f"\n--- TWEET CONTENT ---")
                print(results['content'][:500] if results['content'] else "No content")
                print("--- END CONTENT ---")
            else:
                # Mobile fallback
                text_element = tweet_article.locator('div[lang]').first
                if text_element.count() > 0:
                    results['content'] = text_element.text_content()
                    print(f"\n--- TWEET CONTENT (mobile) ---")
                    print(results['content'][:500] if results['content'] else "No content")
                    print("--- END CONTENT ---")

        # Extract username
        user_name_element = tweet_article.locator('[data-testid="User-Name"]').first
        if user_name_element.count() > 0:
            username_link = user_name_element.locator('a[href^="/"]:not([href*="/status"])').first
            if username_link.count() > 0:
                href = username_link.get_attribute('href')
                if href and href.startswith('/'):
                    results['username'] = href.lstrip('/').split('/')[0].lstrip('@')
                    print(f"\nUsername: @{results['username']}")

        # Extract timestamp
        time_element = tweet_article.locator('time').first
        if time_element.count() > 0:
            results['timestamp'] = time_element.get_attribute('datetime')
            print(f"Timestamp: {results['timestamp']}")

        # Extract metrics
        elements = tweet_article.locator('[aria-label]').all()
        for element in elements:
            try:
                label = element.get_attribute('aria-label') or ''
                label_lower = label.lower()

                if 'repl' in label_lower:
                    results['metrics']['comments'] = parse_count(label)
                elif 'like' in label_lower:
                    results['metrics']['likes'] = parse_count(label)
                elif 'view' in label_lower:
                    results['metrics']['views'] = parse_count(label)
                elif 'quote' in label_lower:
                    results['metrics']['quotes'] = parse_count(label)
                elif 'repost' in label_lower or 'retweet' in label_lower:
                    results['metrics']['reposts'] = parse_count(label)
            except Exception:
                continue

        if results['metrics']:
            print(f"\nMetrics: {results['metrics']}")

        print("\n" + "=" * 60)
        print("SCRAPE RESULT: SUCCESS" if results['content'] else "SCRAPE RESULT: PARTIAL (no content)")

        return results

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        browser.close()
        playwright.stop()


def parse_count(text: str) -> int:
    """Parse count from text like '1.2K', '3M', '42', etc."""
    if not text:
        return 0
    text = str(text).strip().upper().replace(',', '')
    match = re.match(r'([\d\.]+)([KMB])?', text)
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = match.group(2)
    if multiplier == 'K':
        return int(number * 1000)
    elif multiplier == 'M':
        return int(number * 1000000)
    elif multiplier == 'B':
        return int(number * 1000000000)
    return int(number)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        test_url = "https://x.com/i/status/2007023769081028985"

    result = test_scrape_post(test_url, headless=False)
