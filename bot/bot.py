import discord
from discord import app_commands
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv('.env')

config_path = os.path.join('..', 'shared', 'config', 'bot_config.json')
with open(config_path) as f:
    config = json.load(f)

PLATFORMS = {
    'X': ['twitter.com', 'x.com'],
    'Reddit': ['reddit.com']
}

PLATFORM_EMOJIS = {'X': '🐦', 'Reddit': '🔴'}

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials_path = os.path.join('..', 'shared', 'credentials', 'google.json')
CREDS = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, SCOPES)
SHEETS_CLIENT = gspread.authorize(CREDS)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class ContentBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet_id = config['content_sheet_id']
        self.channel_id = int(config['content_channel_id']) if config['content_channel_id'] != 'CHANNEL_ID_HERE' else None

    def detect_platform(self, url):
        url_lower = url.lower()
        for platform, keywords in PLATFORMS.items():
            if any(kw in url_lower for kw in keywords):
                return platform
        return None

    def get_or_create_monthly_tab(self, spreadsheet):
        tab_name = datetime.now().strftime('%m/%y')

        try:
            return spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=15)

            headers = [
                'Date', 'Author', 'URL', 'Impressions', 'Likes', 'Comments', 'Notes', 'Total Impressions',
                'Date', 'Author', 'URL', 'Views', 'Upvotes', 'Comments', 'Notes', 'Total Impressions'
            ]

            worksheet.update('A1:P1', [headers])

            worksheet.format('A:P', {'textFormat': {'fontFamily': 'Lexend', 'fontSize': 12}})

            worksheet.format('A1:H1', {
                'backgroundColor': {'red': 0.53, 'green': 0.81, 'blue': 0.98},
                'textFormat': {'bold': True, 'fontFamily': 'Lexend', 'fontSize': 12},
                'horizontalAlignment': 'CENTER'
            })

            worksheet.format('I1:P1', {
                'backgroundColor': {'red': 1.0, 'green': 0.55, 'blue': 0.27},
                'textFormat': {'bold': True, 'fontFamily': 'Lexend', 'fontSize': 12},
                'horizontalAlignment': 'CENTER'
            })

            return worksheet

    def append_to_table(self, worksheet, platform, data):
        col_config = {
            'X': (1, 'A', 'H'),
            'Reddit': (9, 'I', 'P')
        }

        if platform not in col_config:
            raise ValueError(f"Unknown platform: {platform}")

        start_col, start_letter, end_letter = col_config[platform]
        next_row = len(worksheet.col_values(start_col)) + 1

        # Keep row width aligned with the A:P header structure (include total impressions col).
        row_data = [data['date'], data['author'], data['url'], '', '', '', data['notes'], '']
        worksheet.update(f'{start_letter}{next_row}:{end_letter}{next_row}', [row_data])

    @app_commands.command(name='submit', description='Submit content for a raid')
    @app_commands.describe(link='The URL of your X or Reddit post', notes='Optional notes about the content')
    async def submit(self, interaction: discord.Interaction, link: str, notes: str = ''):
        platform = self.detect_platform(link)
        if not platform:
            await interaction.response.send_message("URL not recognized. Please submit an X or Reddit link.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            spreadsheet = SHEETS_CLIENT.open_by_key(self.sheet_id)
            worksheet = self.get_or_create_monthly_tab(spreadsheet)

            data = {
                'date': datetime.now().strftime('%d/%m/%y'),
                'author': interaction.user.display_name,
                'url': link,
                'notes': notes
            }

            self.append_to_table(worksheet, platform, data)

            embed = discord.Embed(title="🦾 ATTACK", color=0x2d2d2d)
            embed.add_field(name="Platform", value=f"{PLATFORM_EMOJIS.get(platform, '📱')} {platform}", inline=False)
            embed.add_field(name="Posted by", value=f"@{interaction.user.display_name}", inline=False)
            embed.add_field(name="Link", value=link, inline=False)
            if notes:
                embed.add_field(name="Notes", value=notes, inline=False)
            embed.set_footer(text="Go engage! Like, Comment, RT/Upvote")

            message = await interaction.followup.send(content="@everyone", embed=embed)
            await message.add_reaction('✅')

        except Exception as e:
            print(f"Error submitting content: {e}")
            await interaction.followup.send("Failed to save, please try again.", ephemeral=True)

class RegistrationBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet_id = config['registration_sheet_id']
        self.channel_id = int(config['registration_channel_id']) if config['registration_channel_id'] != 'CHANNEL_ID_HERE' else None

    def normalize_x_handle(self, url):
        if not url:
            return ''
        url = url.strip()
        if 'twitter.com/' in url or 'x.com/' in url:
            handle = url.rstrip('/').split('/')[-1]
        else:
            handle = url
        return handle.lstrip('@').lower()

    def normalize_x_profile_url(self, url):
        handle = self.normalize_x_handle(url)
        return f"https://x.com/{handle}" if handle else ''

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

    def normalize_reddit_profile_url(self, url):
        username = self.normalize_reddit_username(url)
        return f"https://www.reddit.com/user/{username}" if username else ''

    @app_commands.command(name='register', description='Register your X and Reddit profiles')
    @app_commands.describe(x_profile='Your X (Twitter) profile URL', reddit_profile='Your Reddit profile URL')
    async def register(self, interaction: discord.Interaction, x_profile: str = '', reddit_profile: str = ''):
        if not x_profile and not reddit_profile:
            await interaction.response.send_message("Please provide at least one profile (X or Reddit).", ephemeral=True)
            return

        if self.channel_id and interaction.channel_id != self.channel_id:
            await interaction.response.send_message("Please use this command in the registration channel only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            spreadsheet = SHEETS_CLIENT.open_by_key(self.sheet_id)
            worksheet = spreadsheet.worksheet('Member Registry')

            discord_usernames = worksheet.col_values(1)
            username = interaction.user.name

            x_handle_normalized = self.normalize_x_handle(x_profile)
            reddit_username_normalized = self.normalize_reddit_username(reddit_profile)

            update_data = [
                username,
                self.normalize_x_profile_url(x_profile),
                self.normalize_reddit_profile_url(reddit_profile),
                x_handle_normalized,
                reddit_username_normalized,
                'active',
                datetime.now().strftime('%Y-%m-%d'),
                '',
                '0'
            ]

            if username in discord_usernames[1:]:
                row_index = discord_usernames.index(username) + 1
                worksheet.update(f'A{row_index}:I{row_index}', [update_data])
                message = "✅ Your profile has been updated successfully!"
            else:
                next_row = len(discord_usernames) + 1
                worksheet.update(f'A{next_row}:I{next_row}', [update_data])
                message = "✅ You have been registered successfully!"

            response_parts = [message, "\n**Registered profiles:**"]
            if x_profile:
                response_parts.append(f"🐦 X: @{self.normalize_x_handle(x_profile)}")
            if reddit_profile:
                response_parts.append(f"🔴 Reddit: u/{self.normalize_reddit_username(reddit_profile)}")

            await interaction.followup.send('\n'.join(response_parts), ephemeral=True)

        except Exception as e:
            print(f"Error during registration: {e}")
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
        await bot.start(os.getenv('KEY'))

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
