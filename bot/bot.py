import discord
from discord import app_commands
from discord.ext import commands
import sys
import csv
import hashlib
import re
from pathlib import Path
from datetime import datetime
import logging
from urllib.parse import urlparse

# Add shared to path for config import
_bot_dir = Path(__file__).resolve().parent
_project_root = _bot_dir.parent
sys.path.insert(0, str(_project_root / "shared"))

from config import discord_token, members_sheet_id, CREDENTIALS_FILE, load_env
from sheets_members_service import SheetsMemberService

load_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database paths
DATABASE_DIR = _project_root / "database"
LINKS_CSV = DATABASE_DIR / "links.csv"
MEMBERS_CSV = DATABASE_DIR / "members.csv"

PLATFORMS = {
    'X': ['twitter.com', 'x.com', 't.co'],
    'Reddit': ['reddit.com', 'redd.it']
}

SUBMIT_CHANNEL_ID = 1468594212692955361

URL_RE = re.compile(r'https?://[^\s<>]+')

PLATFORM_EMOJIS = {'X': '🐦', 'Reddit': '🔴'}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


def _read_csv(path: Path) -> list[dict]:
    """Read CSV file and return list of dicts."""
    if not path.exists():
        return []
    try:
        with path.open('r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to read {path}: {e}")
        return []


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> bool:
    """Write rows to CSV file."""
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


def _normalize_url(url: str) -> str:
    """Normalize X/Twitter URLs to standard format."""
    if not url:
        return url
    match = re.search(r'/status(?:es)?/(\d+)', url)
    if match:
        return f"https://x.com/i/status/{match.group(1)}"
    return url.strip()


def _gen_id(url: str) -> str:
    """Generate short ID from URL."""
    return hashlib.sha1(url.encode()).hexdigest()[:12]


class ContentBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def detect_platform(self, url: str):
        cleaned = (url or '').strip()
        if not cleaned:
            return None

        parsed = urlparse(cleaned if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', cleaned) else f'https://{cleaned}')
        host = (parsed.netloc or parsed.path.split('/')[0]).lower().lstrip('www.')

        for platform, domains in PLATFORMS.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                return platform

        # Fallback for malformed links that still include known domains.
        url_lower = cleaned.lower()
        for platform, domains in PLATFORMS.items():
            if any(domain in url_lower for domain in domains):
                return platform
        return None

    def save_link_to_csv(self, url: str, author: str, platform: str, notes: str = '') -> bool:
        """Save a new link to links.csv."""
        normalized_url = _normalize_url(url)

        # Read existing links
        rows = _read_csv(LINKS_CSV)

        # Check if URL already exists
        for row in rows:
            if row.get('url') == normalized_url:
                logger.info(f"URL already exists: {normalized_url}")
                return True  # Already exists, not an error

        # Add new link
        year_month = datetime.now().strftime('%Y-%m')
        new_row = {
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
            'content': notes if notes else '',
            'title': '',
            'synced_at': '',
        }
        rows.append(new_row)

        fieldnames = ['id', 'platform', 'url', 'author', 'year_month', 'date',
                      'impressions', 'likes', 'comments', 'retweets', 'content', 'title', 'synced_at']

        return _write_csv(LINKS_CSV, rows, fieldnames)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != SUBMIT_CHANNEL_ID:
            return

        urls = URL_RE.findall(message.content)
        for url in urls:
            url = url.rstrip('.,)>"\']')  # strip trailing punctuation Discord may include
            platform = self.detect_platform(url)
            if not platform:
                continue

            try:
                author = message.author.name
                normalized_url = _normalize_url(url)
                success = self.save_link_to_csv(normalized_url, author, platform)

                if not success:
                    logger.error(f"Failed to save link from {author}: {url}")
                    continue

                lines = [
                    "@everyone",
                    f"**🦾 ATTACK** | {PLATFORM_EMOJIS.get(platform, '📱')} {platform} | @{message.author.display_name}",
                ]
                raid_msg = await message.reply(
                    content="\n".join(lines),
                    allowed_mentions=discord.AllowedMentions(everyone=True, roles=False, users=False, replied_user=False),
                )
                await raid_msg.add_reaction('✅')
                await message.add_reaction('✅')

                logger.info(f"Auto-submitted link by {author}: {url} -> {normalized_url}")
                break  # One raid message per original message

            except Exception as e:
                logger.error(f"Error auto-submitting link from {message.author.name}: {e}")


class RegistrationBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._sheets_service = None

    def _get_sheets_service(self) -> SheetsMemberService | None:
        """Lazy-load sheets service for member registration."""
        if self._sheets_service is None:
            sheet_id = members_sheet_id()
            if not sheet_id or not CREDENTIALS_FILE.exists():
                logger.warning("Sheets service unavailable: missing credentials or sheet ID")
                return None
            self._sheets_service = SheetsMemberService(CREDENTIALS_FILE, sheet_id)
        return self._sheets_service

    def save_member_to_sheets(self, discord_user: str, x_handle: str, reddit_username: str) -> bool:
        """Save member directly to Google Sheets (source of truth)."""
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
            # Extract username right after u/ or user/, ignoring /s/shareID suffix
            match = re.search(r'(?:u|user)/([^/]+)', url)
            username = match.group(1) if match else url.split('/')[-1]
        else:
            username = url
        if username.startswith('u/'):
            username = username[2:]
        return username.lower()

    @app_commands.command(name='register', description='Register your X and Reddit profiles')
    @app_commands.describe(x_profile='Your X (Twitter) profile URL', reddit_profile='Your Reddit profile URL')
    async def register(self, interaction: discord.Interaction, x_profile: str = '', reddit_profile: str = ''):
        if not x_profile and not reddit_profile:
            await interaction.response.send_message("Please provide at least one profile (X or Reddit).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            discord_user = interaction.user.name
            x_handle = self.normalize_x_handle(x_profile)
            reddit_username = self.normalize_reddit_username(reddit_profile)

            success = self.save_member_to_sheets(discord_user, x_handle, reddit_username)

            if not success:
                await interaction.followup.send("❌ Failed to register. Please try again.", ephemeral=True)
                return

            response_parts = ["✅ You have been registered successfully!", "\n**Registered profiles:**"]
            if x_profile:
                response_parts.append(f"🐦 X: @{x_handle}")
            if reddit_profile:
                response_parts.append(f"🔴 Reddit: u/{reddit_username}")

            await interaction.followup.send('\n'.join(response_parts), ephemeral=True)

            logger.info(f"Member registered: {discord_user} (X: {x_handle}, Reddit: {reddit_username})")

        except Exception as e:
            logger.error(f"Error during registration: {e}")
            await interaction.followup.send("❌ Failed to register. Please try again.", ephemeral=True)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} command(s)')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')


async def setup():
    await bot.add_cog(ContentBot(bot))
    await bot.add_cog(RegistrationBot(bot))


async def main():
    async with bot:
        await setup()
        await bot.start(discord_token())


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
