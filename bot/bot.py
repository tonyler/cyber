import asyncio
import csv
import hashlib
import json
import logging
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

# Add shared to path for config import
_bot_dir = Path(__file__).resolve().parent
_project_root = _bot_dir.parent
sys.path.insert(0, str(_project_root / "shared"))

from config import (
    CREDENTIALS_FILE,
    discord_guild_id,
    discord_token,
    load_env,
    anthropic_api_key,
    anthropic_model,
    members_sheet_id,
    submit_channel_id,
)
from sheets_members_service import SheetsMemberService

load_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
DATABASE_DIR = _project_root / "database"
LINKS_CSV = DATABASE_DIR / "links.csv"
MEMBERS_CSV = DATABASE_DIR / "members.csv"
ATTACK_MESSAGES_CSV = DATABASE_DIR / "attack_messages.csv"
PROPOSALS_CSV = DATABASE_DIR / "comment_proposals.csv"
SCRAPED_DIR = DATABASE_DIR / "scraped"
PROMPT_INSTRUCTIONS_FILE = _bot_dir / "prompt_instructions.md"

# ── Constants ────────────────────────────────────────────────────────────────
PLATFORMS = {
    'X': ['twitter.com', 'x.com', 't.co'],
    'Reddit': ['reddit.com', 'redd.it'],
}
SUBMIT_CHANNEL_ID: int = submit_channel_id()
URL_RE = re.compile(r'https?://[^\s<>]+')
PLATFORM_EMOJIS = {'X': '🐦', 'Reddit': '🔴'}
PLATFORM_COLORS = {'X': 0x000000, 'Reddit': 0xFF4500}
PROPOSAL_RETENTION_DAYS = 7

# Resolved on startup: the single guild the bot is allowed to operate in.
_allowed_guild_id: int | None = None

# Shared in-memory cache: attack message ID → {url, instructions, content}
# Populated on startup from CSV and updated live as new attack messages are sent.
# `content` starts as None (scrape pending), becomes '' (failed) or text (success).
_attack_cache: dict[str, dict] = {}

# Tracks message IDs whose scrape task is currently running — prevents duplicate scrapes.
_scraping_in_progress: set[str] = set()

# X session file — checked in order
_X_SESSION_PATHS = [
    _project_root / "cookies.json",
    _project_root / "shared" / "x_session.json",
]
_X_DOMAINS = {'x.com', 'twitter.com', 'api.x.com', 'upload.x.com'}

# Tracks message IDs whose scrape task is currently running — prevents duplicate scrapes.
_scraping_in_progress: set[str] = set()


# ── Scrape file helpers ───────────────────────────────────────────────────────
# One JSON file per attack message in database/scraped/{message_id}.json
# Fields: message_id, url, content, scraped (bool), scraped_at (ISO datetime)
# scraped=True  → content is cached, skip re-scraping
# scraped=False → scrape failed or pending; will retry
# Files older than 7 days are deleted so fresh content can be fetched

def _scrape_path(msg_id: str) -> Path:
    return SCRAPED_DIR / f"{msg_id}.json"


def _get_scrape(msg_id: str) -> dict | None:
    """Return scrape record for this message, or None if file doesn't exist."""
    p = _scrape_path(msg_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Failed to read scrape file {p}: {e}")
        return None


def _save_scrape(msg_id: str, url: str, content: str, scraped: bool) -> None:
    """Persist scrape result to its JSON file."""
    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        'message_id': msg_id,
        'url': url,
        'content': content,
        'scraped': scraped,
        'scraped_at': datetime.now().isoformat(),
    }
    try:
        _scrape_path(msg_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    except Exception as e:
        logger.error(f"Failed to write scrape file for {msg_id}: {e}")


async def _scrape_tweet_text(url: str) -> str:
    """Scrape tweet text via authenticated async Playwright. Returns '' on failure."""
    from playwright.async_api import async_playwright

    session_file = next((p for p in _X_SESSION_PATHS if p.exists()), None)
    if not session_file:
        logger.warning("No X session file found — cannot scrape tweet content")
        return ''

    try:
        raw = json.loads(session_file.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Failed to read X session file: {e}")
        return ''

    all_cookies = raw if isinstance(raw, list) else raw.get('cookies', [])
    playwright_cookies = [
        {
            'name': c['name'],
            'value': c['value'],
            'domain': c.get('domain', 'x.com'),
            'path': c.get('path', '/'),
            'secure': c.get('secure', True),
            'httpOnly': c.get('httpOnly', False),
            'sameSite': c.get('sameSite', 'None') if c.get('sameSite') in ('Strict', 'Lax', 'None') else 'None',
        }
        for c in all_cookies
        if c.get('domain', '').lstrip('.') in _X_DOMAINS and c.get('name') and c.get('value')
    ]

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage',
                      '--disable-blink-features=AutomationControlled'],
            )
            context = await browser.new_context(
                viewport={'width': 390, 'height': 844},
                user_agent=(
                    'Mozilla/5.0 (Linux; Android 14; Pixel 8) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Mobile Safari/537.36'
                ),
                is_mobile=True,
                has_touch=True,
                locale='en-US',
                ignore_https_errors=True,
            )
            if playwright_cookies:
                await context.add_cookies(playwright_cookies)

            page = await context.new_page()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await page.wait_for_selector('article', timeout=12000)
                await page.wait_for_timeout(1500)

                # Find the article that belongs to the target tweet
                tweet_id_match = re.search(r'/status/(\d+)', url)
                tweet_id = tweet_id_match.group(1) if tweet_id_match else None
                target = None

                if tweet_id:
                    for article in await page.locator('article').all():
                        for tl in await article.locator('time').locator('xpath=..').all():
                            if f'/status/{tweet_id}' in (await tl.get_attribute('href') or ''):
                                target = article
                                break
                        if target:
                            break

                if target is None:
                    articles = await page.locator('article').all()
                    target = articles[0] if articles else None

                if target is None:
                    return ''

                text_el = target.locator('[data-testid="tweetText"]').first
                if await text_el.count() > 0:
                    return (await text_el.text_content() or '').strip()
                return ''
            finally:
                await page.close()
                await context.close()
                await browser.close()
    except Exception as e:
        logger.error(f"Tweet scrape failed for {url}: {e}")
        return ''


async def _scrape_and_cache(msg_id: str, url: str) -> str:
    """Scrape tweet text and persist to database/scraped/{msg_id}.json.

    Returns scraped content (empty string if failed).
    Skips if already scraped (scraped=True in file) or scrape already in progress.
    """
    # Already scraped successfully — return cached content, no re-scrape
    existing = _get_scrape(msg_id)
    if existing and existing.get('scraped'):
        logger.info(f"Already scraped {url} — skipping")
        return existing.get('content', '')

    # Scrape already running for this message — don't duplicate
    if msg_id in _scraping_in_progress:
        logger.info(f"Scrape already in progress for {url} — skipping")
        return ''

    _scraping_in_progress.add(msg_id)
    try:
        logger.info(f"Scraping tweet content for {url} …")
        content = await _scrape_tweet_text(url)
        success = bool(content)
        _save_scrape(msg_id, url, content, scraped=success)
        if success:
            logger.info(f"Scraped {url} ({len(content)} chars): {content!r}")
        else:
            logger.warning(f"No content scraped for {url} — saved with scraped=False")
        return content
    finally:
        _scraping_in_progress.discard(msg_id)


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open('r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to read {path}: {e}")
        return []


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        return True
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        return False


# ── URL helpers ───────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    if not url:
        return url
    match = re.search(r'/status(?:es)?/(\d+)', url)
    if match:
        return f"https://x.com/i/status/{match.group(1)}"
    return url.strip()


def _gen_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


# ── Attack message cache helpers ──────────────────────────────────────────────

def _load_attack_cache() -> None:
    """Populate the in-memory cache from the persisted CSV."""
    rows = _read_csv(ATTACK_MESSAGES_CSV)
    for row in rows:
        msg_id = row.get('message_id', '').strip()
        if msg_id:
            _attack_cache[msg_id] = {
                'url': row.get('url', ''),
                'author_id': row.get('author_id', ''),
                'instructions': row.get('instructions', ''),
            }
    logger.info(f"Loaded {len(_attack_cache)} attack message(s) from cache")


_ATTACK_CSV_FIELDS = ['message_id', 'url', 'author_id', 'instructions', 'content', 'created_at']


def _persist_attack_message(message_id: str, url: str, author_id: str, instructions: str) -> None:
    rows = _read_csv(ATTACK_MESSAGES_CSV)
    if any(r.get('message_id') == message_id for r in rows):
        return
    rows.append({
        'message_id': message_id,
        'url': url,
        'author_id': author_id,
        'instructions': instructions,
        'content': '',
        'created_at': datetime.now().isoformat(),
    })
    _write_csv(ATTACK_MESSAGES_CSV, rows, _ATTACK_CSV_FIELDS)


def _persist_attack_instructions(message_id: str, instructions: str) -> None:
    rows = _read_csv(ATTACK_MESSAGES_CSV)
    for row in rows:
        if row.get('message_id') == message_id:
            row['instructions'] = instructions
            break
    _write_csv(ATTACK_MESSAGES_CSV, rows, _ATTACK_CSV_FIELDS)


def _cleanup_old_data() -> None:
    """Remove old proposals; clear scraped content from attack messages older than 7 days."""
    cutoff = datetime.now() - timedelta(days=PROPOSAL_RETENTION_DAYS)

    # Drop old comment proposals entirely
    rows = _read_csv(PROPOSALS_CSV)
    if rows:
        fresh = []
        for row in rows:
            try:
                if datetime.fromisoformat(row.get('proposed_at', '')) >= cutoff:
                    fresh.append(row)
            except (ValueError, TypeError):
                fresh.append(row)
        removed = len(rows) - len(fresh)
        if removed:
            _write_csv(PROPOSALS_CSV, fresh, list(rows[0].keys()))
            logger.info(f"Cleaned {removed} old proposals from {PROPOSALS_CSV.name}")

    # Delete scrape files older than 7 days so content is re-fetched when needed
    if SCRAPED_DIR.exists():
        deleted = 0
        for p in SCRAPED_DIR.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding='utf-8'))
                scraped_at = datetime.fromisoformat(rec.get('scraped_at', ''))
                if scraped_at < cutoff:
                    p.unlink()
                    deleted += 1
            except Exception:
                pass
        if deleted:
            logger.info(f"Deleted {deleted} old scrape file(s) from {SCRAPED_DIR.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Cog: ContentBot — auto-submit links from the submit channel
# ═══════════════════════════════════════════════════════════════════════════════

class ContentBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def detect_platform(self, url: str):
        cleaned = (url or '').strip()
        if not cleaned:
            return None
        parsed = urlparse(
            cleaned if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', cleaned)
            else f'https://{cleaned}'
        )
        host = (parsed.netloc or parsed.path.split('/')[0]).lower().lstrip('www.')
        for platform, domains in PLATFORMS.items():
            if any(host == d or host.endswith(f".{d}") for d in domains):
                return platform
        url_lower = cleaned.lower()
        for platform, domains in PLATFORMS.items():
            if any(d in url_lower for d in domains):
                return platform
        return None

    def save_link_to_csv(self, url: str, author: str, platform: str, notes: str = '') -> bool:
        normalized_url = _normalize_url(url)
        rows = _read_csv(LINKS_CSV)
        for row in rows:
            if row.get('url') == normalized_url:
                logger.info(f"URL already exists: {normalized_url}")
                return True
        year_month = datetime.now().strftime('%Y-%m')
        rows.append({
            'id': _gen_id(normalized_url),
            'platform': platform.lower(),
            'url': normalized_url,
            'author': author,
            'year_month': year_month,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'impressions': '',
            'likes': '',
            'comments': '',
            'retweets': '',
            'content': notes,
            'title': '',
            'synced_at': '',
        })
        fieldnames = [
            'id', 'platform', 'url', 'author', 'year_month', 'date',
            'impressions', 'likes', 'comments', 'retweets', 'content', 'title', 'synced_at',
        ]
        return _write_csv(LINKS_CSV, rows, fieldnames)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if _allowed_guild_id and message.guild and message.guild.id != _allowed_guild_id:
            return
        if message.channel.id != SUBMIT_CHANNEL_ID:
            return

        # Extract optional author instructions from text after "|"
        # Example: "https://x.com/post | ask about AI safety, keep it conversational"
        instructions = ''
        if '|' in message.content:
            instructions = message.content.split('|', 1)[1].strip()

        urls = URL_RE.findall(message.content)
        for url in urls:
            url = url.rstrip('.,)>"\']')
            platform = self.detect_platform(url)
            if not platform:
                continue

            try:
                author = message.author.name
                normalized_url = _normalize_url(url)
                success = self.save_link_to_csv(normalized_url, author, platform, instructions)

                if not success:
                    logger.error(f"Failed to save link from {author}: {url}")
                    continue

                raid_msg = await message.channel.send(
                    content=f"@everyone {normalized_url}",
                    allowed_mentions=discord.AllowedMentions(
                        everyone=True, roles=False, users=False
                    ),
                )
                await raid_msg.add_reaction('✅')
                await raid_msg.add_reaction('💬')
                await raid_msg.add_reaction('❌')

                try:
                    await message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete original message: {e}")

                # Cache this attack message so /help can retrieve post data later
                msg_id_str = str(raid_msg.id)
                author_id = str(message.author.id)
                _attack_cache[msg_id_str] = {
                    'url': normalized_url,
                    'author_id': author_id,
                    'instructions': instructions,
                }
                _persist_attack_message(msg_id_str, normalized_url, author_id, instructions)

                # Scrape X post content in the background — ready before anyone types /help
                if platform == 'X':
                    asyncio.create_task(_scrape_and_cache(msg_id_str, normalized_url))

                logger.info(f"Auto-submitted link by {author}: {url} -> {normalized_url}")
                break  # one raid message per original message

            except Exception as e:
                logger.error(f"Error auto-submitting link from {message.author.name}: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        msg_id = str(payload.message_id)
        post_data = _attack_cache.get(msg_id)

        # ── ❌ Author disables comment generation for this post ───────────────
        if emoji == '❌' and post_data and str(payload.user_id) == post_data.get('author_id'):
            post_data['comments_disabled'] = True
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(payload.message_id)
                    user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                    await msg.remove_reaction('❌', user)
                    # Remove 💬 so members know comment help is off
                    await msg.clear_reaction('💬')
                except Exception as e:
                    logger.warning(f"Could not update reactions after ❌: {e}")
            try:
                author = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                if author:
                    await author.send(
                        f"🚫 Comment generation **disabled** for this post.\n"
                        f"Members can no longer request AI comment suggestions for it."
                    )
            except discord.Forbidden:
                pass
            logger.info(f"Comment generation disabled for msg {msg_id} by author {payload.user_id}")
            return

        if emoji != '💬':
            return

        if not post_data:
            return

        # Check if author has disabled comment generation
        if post_data.get('comments_disabled'):
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(payload.message_id)
                    user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                    await msg.remove_reaction('💬', user)
                except Exception:
                    pass
            try:
                user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                if user:
                    await user.send("🚫 The post author has disabled AI comment suggestions for this post.")
            except discord.Forbidden:
                pass
            return

        # Remove the user's reaction immediately
        channel = self.bot.get_channel(payload.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(payload.message_id)
                user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                await msg.remove_reaction('💬', user)
            except Exception as e:
                logger.warning(f"Could not remove 💬 reaction: {e}")

        user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
        if not user:
            return

        # Get AI cog for generation
        cog: AICommentBot = self.bot.cogs.get('AICommentBot')
        if not cog:
            return

        # Check scrape file — if scraped=True, content is ready; no re-scraping needed
        scrape = _get_scrape(msg_id)
        post_content = scrape.get('content', '') if (scrape and scrape.get('scraped')) else ''

        if not post_content:
            if msg_id in _scraping_in_progress:
                # Background scrape is running — wait for it
                try:
                    await user.send("⏳ Fetching post content, please wait a moment…")
                except discord.Forbidden:
                    pass
                for _ in range(12):
                    await asyncio.sleep(2)
                    s = _get_scrape(msg_id)
                    if s and s.get('scraped'):
                        post_content = s.get('content', '')
                        break
            else:
                # No scrape in progress — do it now
                try:
                    await user.send("⏳ Scraping post content, this may take a moment…")
                except discord.Forbidden:
                    pass
                post_content = await _scrape_and_cache(msg_id, post_data['url'])

        comment, draw = await cog._generate_comment(
            post_data['url'],
            post_data['instructions'],
            str(user.id),
            post_content,
        )

        if not comment:
            try:
                await user.send("❌ Couldn't generate a suggestion — try again later.")
            except discord.Forbidden:
                pass
            return

        try:
            await user.send(comment)
        except discord.Forbidden:
            if channel:
                await channel.send(
                    f"{user.mention} 💬 {comment}",
                    delete_after=60,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Cog: RegistrationBot — /register slash command
# ═══════════════════════════════════════════════════════════════════════════════

class RegistrationBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._sheets_service = None

    def _get_sheets_service(self) -> SheetsMemberService | None:
        if self._sheets_service is None:
            sheet_id = members_sheet_id()
            if not sheet_id or not CREDENTIALS_FILE.exists():
                logger.warning("Sheets service unavailable: missing credentials or sheet ID")
                return None
            self._sheets_service = SheetsMemberService(CREDENTIALS_FILE, sheet_id)
        return self._sheets_service

    def save_member_to_sheets(self, discord_user: str, x_handle: str, reddit_username: str) -> bool:
        service = self._get_sheets_service()
        if not service:
            logger.error("Cannot save to sheets: service unavailable")
            return False
        return service.upsert_member(discord_user, x_handle, reddit_username)

    def normalize_x_handle(self, url):
        if not url:
            return ''
        url = url.strip()
        if 'twitter.com/' in url or 'x.com/' in url:
            handle = url.rstrip('/').split('/')[-1]
        else:
            handle = url
        return handle.lstrip('@').lower()

    def normalize_reddit_username(self, url):
        if not url:
            return ''
        url = url.strip()
        if 'reddit.com/' in url and ('u/' in url or 'user/' in url):
            match = re.search(r'(?:u|user)/([^/]+)', url)
            username = match.group(1) if match else url.split('/')[-1]
        else:
            username = url
        if username.startswith('u/'):
            username = username[2:]
        return username.lower()

    @app_commands.command(name='register', description='Register your X and Reddit profiles')
    @app_commands.describe(
        x_profile='Your X (Twitter) profile URL',
        reddit_profile='Your Reddit profile URL',
    )
    async def register(
        self,
        interaction: discord.Interaction,
        x_profile: str = '',
        reddit_profile: str = '',
    ):
        if not x_profile and not reddit_profile:
            await interaction.response.send_message(
                "Please provide at least one profile (X or Reddit).", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            discord_user = interaction.user.name
            x_handle = self.normalize_x_handle(x_profile)
            reddit_username = self.normalize_reddit_username(reddit_profile)

            success = self.save_member_to_sheets(discord_user, x_handle, reddit_username)
            if not success:
                await interaction.followup.send(
                    "❌ Failed to register. Please try again.", ephemeral=True
                )
                return

            parts = ["✅ You have been registered successfully!", "\n**Registered profiles:**"]
            if x_profile:
                parts.append(f"🐦 X: @{x_handle}")
            if reddit_profile:
                parts.append(f"🔴 Reddit: u/{reddit_username}")

            await interaction.followup.send('\n'.join(parts), ephemeral=True)
            logger.info(f"Member registered: {discord_user} (X: {x_handle}, Reddit: {reddit_username})")

        except Exception as e:
            logger.error(f"Error during registration: {e}")
            await interaction.followup.send(
                "❌ Failed to register. Please try again.", ephemeral=True
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Cog: AICommentBot — /help + /suggest slash commands (both ephemeral)
# ═══════════════════════════════════════════════════════════════════════════════

class AICommentBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Proposal tracking ─────────────────────────────────────────────────────

    def _get_existing_proposals(self, post_url: str) -> list[str]:
        """Return comments already suggested for this post (for dedup)."""
        rows = _read_csv(PROPOSALS_CSV)
        return [r['comment'] for r in rows if r.get('post_url') == post_url]

    def _save_proposal(self, post_url: str, user_id: str, comment: str) -> None:
        rows = _read_csv(PROPOSALS_CSV)
        rows.append({
            'post_url': post_url,
            'user_id': user_id,
            'comment': comment,
            'proposed_at': datetime.now().isoformat(),
        })
        _write_csv(PROPOSALS_CSV, rows, ['post_url', 'user_id', 'comment', 'proposed_at'])

    # ── Comment generation ────────────────────────────────────────────────────

    async def _generate_comment(
        self, post_url: str, instructions: str, user_id: str, post_content: str = ''
    ) -> tuple[str, str] | tuple[None, None]:
        """Call Claude to generate a comment."""
        import httpx

        ant_key = anthropic_api_key()
        if not ant_key:
            logger.error("ANTHROPIC_API_KEY not configured")
            return None, None

        existing = self._get_existing_proposals(post_url)

        if not post_content:
            logger.warning(f"No post content for {post_url} — comment quality will be lower")

        # Load stable prompt guidance
        system_prompt = ''
        if PROMPT_INSTRUCTIONS_FILE.exists():
            system_prompt = PROMPT_INSTRUCTIONS_FILE.read_text(encoding='utf-8')

        # Inject curated real examples if available
        examples_file = _bot_dir / "example_comments.md"
        if examples_file.exists():
            examples_text = examples_file.read_text(encoding='utf-8').strip()
            if examples_text:
                system_prompt += f"\n\nExamples of the style we want (real comments from our community):\n{examples_text}"

        # Raffle each dimension independently — compose minimal injected line
        length = random.choice([
            "1-4 words", "one sentence", "5-12 words",
            "incomplete sentence", "2-3 sentences", "short paragraph", "up to 3 paragraphs",
        ])
        style = random.choice([
            "all lowercase", "normal caps", "sloppy caps, typos ok",
            "casual readable", "mix of lowercase and caps", "punchy short sentences",
        ])
        tone = random.choice([
            "agreeable", "quietly excited", "make a question", "matter-of-fact", "genuine",
        ])
        depth = random.choice([
            "pure reaction", "one observation", "question only",
            "one argument", "one concrete detail",
        ])
        voice = random.choice([
            "casual crypto follower", "conviction holder who thinks in years",
            "lurker", "half-paying attention", "opinionated but lazy",
            "non-native English speaker keeping it short",
        ])

        draw = f"{voice} / {tone} / {style} / {length} / {depth}"
        logger.info(f"Comment draw: {draw!r} | instructions={instructions!r}")

        user_parts = [post_content[:2000] if post_content else post_url]
        if instructions:
            user_parts.append(f"angle: {instructions}")
        user_parts.append(f"reply as: {draw}")
        if existing:
            user_parts.append(
                "Already suggested to other users — do NOT repeat, paraphrase, or make the same underlying argument:\n"
                + '\n'.join(f"- {c}" for c in existing[-20:])
            )

        user_message = '\n\n'.join(user_parts)

        try:
            headers = {
                'x-api-key': ant_key,
                'anthropic-version': '2023-06-01',
                'anthropic-beta': 'prompt-caching-2024-07-31',
                'content-type': 'application/json',
            }
            payload = {
                'model': anthropic_model(),
                'max_tokens': 300,
                'system': [{'type': 'text', 'text': system_prompt, 'cache_control': {'type': 'ephemeral'}}],
                'messages': [{'role': 'user', 'content': user_message}],
                'temperature': 1.0,
            }
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post('https://api.anthropic.com/v1/messages', headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                comment = data['content'][0]['text'].strip() if data.get('content') else None

            if comment:
                self._save_proposal(post_url, user_id, comment)
                logger.info(f"Generated comment for {post_url}: {comment}")
            return (comment, draw) if comment else (None, None)
        except Exception as e:
            logger.error(f"Comment generation failed: {e}")
            return None, None

    # ── Delivery helpers ──────────────────────────────────────────────────────

    async def _deliver_comment(
        self,
        recipient: discord.User | discord.Member,
        post_url: str,
        comment: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Send the suggested comment via DM; fall back to a temp channel message."""
        try:
            await recipient.send(comment)
        except discord.Forbidden:
            if channel:
                await channel.send(
                    f"{recipient.mention} 💬 {comment}",
                    delete_after=60,
                )
            else:
                logger.warning(f"Could not DM {recipient} and no fallback channel available")

    # ── /suggest slash command — post author sets instructions for their raid ──

    @app_commands.command(
        name='suggest',
        description='Set comment style instructions for your post (only you can do this)',
    )
    @app_commands.describe(instructions='Tell members how to comment — tone, angle, what to focus on')
    async def suggest(self, interaction: discord.Interaction, instructions: str):
        if _allowed_guild_id and interaction.guild_id != _allowed_guild_id:
            await interaction.response.send_message("Not available here.", ephemeral=True)
            return
        if interaction.channel_id != SUBMIT_CHANNEL_ID:
            await interaction.response.send_message(
                "Use this in the raid channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)

        # Find this user's most recent attack message
        own_entries = [
            (msg_id, data) for msg_id, data in _attack_cache.items()
            if data.get('author_id') == user_id
        ]
        if not own_entries:
            await interaction.followup.send(
                "No post found from you. Submit a link first.", ephemeral=True
            )
            return

        msg_id, data = max(own_entries, key=lambda x: int(x[0]))
        _attack_cache[msg_id]['instructions'] = instructions
        _persist_attack_instructions(msg_id, instructions)

        logger.info(f"Author {user_id} set instructions for {data['url']}: {instructions!r}")

        # Reply publicly to the attack message so the team sees the updated angle
        try:
            attack_msg = await interaction.channel.fetch_message(int(msg_id))
            # Detect platform from cached URL to rebuild the embed cleanly
            cached_url = data.get('url', '')
            platform = next(
                (p for p, domains in PLATFORMS.items()
                 if any(d in cached_url for d in domains)),
                'X'
            )
            updated_embed = discord.Embed(
                title="New Post",
                url=cached_url,
                color=PLATFORM_COLORS.get(platform, 0x5865F2),
            )
            await attack_msg.edit(embed=updated_embed)
            await attack_msg.reply(
                f"📋 **Angle updated** by {interaction.user.mention}: *{instructions}*",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except Exception as e:
            logger.warning(f"Could not update attack message embed: {e}")

        await interaction.followup.send("✅ Instructions saved.", ephemeral=True)




# ═══════════════════════════════════════════════════════════════════════════════
# Context menu — right-click an attack message → Apps → "Get comment"
# (Must be module-level; discord.py does not support context menus inside Cogs)
# ═══════════════════════════════════════════════════════════════════════════════

@app_commands.context_menu(name='Get comment')
async def get_comment_menu(interaction: discord.Interaction, message: discord.Message):
    if _allowed_guild_id and interaction.guild_id != _allowed_guild_id:
        await interaction.response.send_message("Not available here.", ephemeral=True)
        return

    post_data = _attack_cache.get(str(message.id))
    if not post_data:
        await interaction.response.send_message(
            "This message isn't a raid target.", ephemeral=True
        )
        return

    if post_data.get('comments_disabled'):
        await interaction.response.send_message(
            "🚫 The post author has disabled AI comment suggestions for this post.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    cog: AICommentBot = interaction.client.cogs.get('AICommentBot')
    if not cog:
        await interaction.followup.send("Bot error — try again later.", ephemeral=True)
        return

    msg_id_str = str(message.id)
    # Check scrape file — if scraped=True, use cached content; skip re-scraping
    scrape = _get_scrape(msg_id_str)
    post_content = scrape.get('content', '') if (scrape and scrape.get('scraped')) else ''

    scraping_msg = None
    if not post_content:
        scraping_msg = await interaction.followup.send(
            "⏳ Scraping post content, this may take a moment…", ephemeral=True, wait=True
        )
        post_content = await _scrape_and_cache(msg_id_str, post_data['url'])

    comment, draw = await cog._generate_comment(
        post_data['url'],
        post_data['instructions'],
        str(interaction.user.id),
        post_content,
    )

    result_text = comment if comment else "❌ Couldn't generate a suggestion — try again later."

    if scraping_msg:
        await scraping_msg.edit(content=result_text)
    else:
        await interaction.followup.send(result_text, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Bot lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    global _allowed_guild_id
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    _load_attack_cache()
    _cleanup_old_data()

    # Resolve allowed guild: prefer env var, fall back to guild containing submit channel.
    configured_guild_id = discord_guild_id()
    if configured_guild_id:
        _allowed_guild_id = configured_guild_id
    else:
        channel = bot.get_channel(SUBMIT_CHANNEL_ID)
        if channel and hasattr(channel, 'guild'):
            _allowed_guild_id = channel.guild.id
            logger.info(f'Auto-detected guild from submit channel: {channel.guild.name} ({_allowed_guild_id})')

    # Sync slash commands only to the allowed guild (instant + scoped).
    if _allowed_guild_id:
        allowed_guild = discord.Object(id=_allowed_guild_id)
        try:
            bot.tree.copy_global_to(guild=allowed_guild)
            synced = await bot.tree.sync(guild=allowed_guild)
            logger.info(f'Synced {len(synced)} command(s) to guild {_allowed_guild_id}')
        except Exception as e:
            logger.error(f'Failed to sync commands to guild {_allowed_guild_id}: {e}')
    else:
        logger.warning('No guild restriction set — syncing to all guilds')
        total = 0
        for guild in bot.guilds:
            try:
                synced = await bot.tree.sync(guild=guild)
                total += len(synced)
            except Exception as e:
                logger.error(f'Failed to sync commands to guild {guild.id}: {e}')
        logger.info(f'Synced to {len(bot.guilds)} guild(s)')


_RAID_CALL_CHANNEL_ID = 1516155219442925819


async def setup():
    await bot.add_cog(ContentBot(bot))
    await bot.add_cog(RegistrationBot(bot))
    await bot.add_cog(AICommentBot(bot))
    bot.tree.add_command(get_comment_menu)

    _WHOISHERE_ALLOWED_USERS = {
        817451374811152474,
        323552635875753984,
        841231271896023061,
        795729591212834847,
        839948301440122880,
        481575480852480001,
        601367595282857995,
        839212513673347142,
        434859163915386893,
        383745004364890113,
    }

    @bot.tree.command(name='whoishere', description='List who is currently in a voice channel')
    @app_commands.describe(channel='The voice channel to scan (defaults to the raid call channel)')
    async def whoishere(interaction: discord.Interaction, channel: discord.VoiceChannel | None = None):
        if interaction.user.id not in _WHOISHERE_ALLOWED_USERS:
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        if _allowed_guild_id and interaction.guild_id != _allowed_guild_id:
            await interaction.response.send_message("Not available here.", ephemeral=True)
            return

        target_channel = channel or interaction.guild.get_channel(_RAID_CALL_CHANNEL_ID)
        if target_channel is None:
            await interaction.response.send_message("Couldn't find that voice channel.", ephemeral=True)
            return

        members = target_channel.members
        if not members:
            await interaction.response.send_message(
                f"**{target_channel.name}** is empty right now.", ephemeral=True
            )
            return

        lines = [
            m.display_name + (f" ({m.name})" if m.display_name != m.name else "")
            for m in members
        ]
        txt_content = f"{target_channel.name} — {len(members)} member(s)\n\n" + "\n".join(lines)
        file = discord.File(
            fp=__import__('io').BytesIO(txt_content.encode()),
            filename="whoishere.txt",
        )
        await interaction.response.send_message(
            f"**{target_channel.name}** — {len(members)} member(s) in call",
            file=file,
            ephemeral=True,
        )


async def main():
    async with bot:
        await setup()
        await bot.start(discord_token())


if __name__ == '__main__':
    asyncio.run(main())
