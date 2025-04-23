import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dtime
import pytz
import asyncio

from utils import calculate_oil_summary  # Ensure your logic is in a utils file
from gsheet_logger import log_to_sheet  # Your Google Sheets handler

TOKEN = os.getenv("TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# Channel IDs
OIL_LOG_CHANNEL_ID = 1347225637949149285
REPORT_CHANNEL_ID = 1347192193453916171

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    daily_summary.start()

# ---------------------- Auto Daily Summary Task ----------------------
@tasks.loop(time=dtime(hour=19, minute=40, tzinfo=pytz.timezone("Asia/Kolkata")))
async def daily_summary():
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    yesterday = now - timedelta(days=1)

    oil_log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    report_channel = bot.get_channel(REPORT_CHANNEL_ID)

    if oil_log_channel and report_channel:
        messages = await oil_log_channel.history(after=yesterday, before=now, limit=None).flatten()
        summary = calculate_oil_summary(messages)
        await report_channel.send(f"**Daily Oil Summary ({yesterday.strftime('%b %d %H:%M')} - {now.strftime('%b %d %H:%M')})**\n{summary}")
        log_to_sheet(messages)  # Logs to Google Sheet

# ---------------------- Manual Command ----------------------
@bot.command()
async def oil_summary(ctx, start: str, end: str):
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        oil_log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
        messages = await oil_log_channel.history(after=start_dt, before=end_dt, limit=None).flatten()
        summary = calculate_oil_summary(messages)
        await ctx.send(f"**Oil Summary** from {start_dt} to {end_dt}:\n{summary}")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

bot.run(TOKEN)
