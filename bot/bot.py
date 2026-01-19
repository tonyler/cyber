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
    'X': ['twitter.com', 'x.com'],
    'Reddit': ['reddit.com']
}

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

    def detect_platform(self, url):
        url_lower = url.lower()
        for platform, keywords in PLATFORMS.items():
            if any(kw in url_lower for kw in keywords):
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

    @app_commands.command(name='submit', description='Submit content for a raid')
    @app_commands.describe(link='The URL of your X or Reddit post', notes='Optional notes about the content')
    async def submit(self, interaction: discord.Interaction, link: str, notes: str = ''):
        platform = self.detect_platform(link)
        if not platform:
            await interaction.response.send_message("URL not recognized. Please submit an X or Reddit link.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            author = interaction.user.name
            success = self.save_link_to_csv(link, author, platform, notes)

            if not success:
                await interaction.followup.send("Failed to save, please try again.", ephemeral=True)
                return

            embed = discord.Embed(title="🦾 ATTACK", color=0x2d2d2d)
            embed.add_field(name="Platform", value=f"{PLATFORM_EMOJIS.get(platform, '📱')} {platform}", inline=False)
            embed.add_field(name="Posted by", value=f"@{interaction.user.display_name}", inline=False)
            embed.add_field(name="Link", value=link, inline=False)
            if notes:
                embed.add_field(name="Notes", value=notes, inline=False)
            embed.set_footer(text="Go engage! Like, Comment, RT/Upvote")

            message = await interaction.followup.send(content="@everyone", embed=embed)
            await message.add_reaction('✅')

            logger.info(f"Link submitted by {author}: {link}")

        except Exception as e:
            logger.error(f"Error submitting content: {e}")
            await interaction.followup.send("Failed to save, please try again.", ephemeral=True)


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
            username = url.rstrip('/').split('/')[-1]
        else:
            username = url
        if username.startswith('u/'):
            username = username[2:]
        return username.lower()

    def save_member_to_csv(self, discord_user: str, x_handle: str, reddit_username: str) -> bool:
        """Save or update member in members.csv."""
        rows = _read_csv(MEMBERS_CSV)

        # Find existing member
        found = False
        discord_lower = discord_user.lower()
        for row in rows:
            if row.get('discord_user', '').lower() == discord_lower:
                # Update existing
                row['x_handle'] = x_handle
                row['reddit_username'] = reddit_username
                row['last_active'] = datetime.now().strftime('%Y-%m-%d')
                found = True
                break

        if not found:
            # Add new member
            new_row = {
                'discord_user': discord_user,
                'x_handle': x_handle,
                'reddit_username': reddit_username,
                'status': 'active',
                'joined_date': datetime.now().strftime('%Y-%m-%d'),
                'last_activity': '',
                'total_points': '0',
                'last_active': datetime.now().strftime('%Y-%m-%d'),
                'total_tasks': '',
                'x_profile_url': f'https://x.com/{x_handle}' if x_handle else '',
                'reddit_profile_url': f'https://reddit.com/user/{reddit_username}' if reddit_username else '',
                'registration_date': datetime.now().strftime('%Y-%m-%d'),
            }
            rows.append(new_row)

        fieldnames = ['discord_user', 'x_handle', 'reddit_username', 'status',
                      'joined_date', 'last_activity', 'total_points', 'last_active',
                      'total_tasks', 'x_profile_url', 'reddit_profile_url', 'registration_date']

        return _write_csv(MEMBERS_CSV, rows, fieldnames)

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
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')


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
