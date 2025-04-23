import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dtime
import pytz
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ENV
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = json.loads(os.getenv("GOOGLE_CREDS_JSON"))

# IDs
OIL_LOG_CHANNEL_ID = 1347225637949149285
REPORT_CHANNEL_ID = 1347192193453916171

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Google Sheet setup
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS_JSON, scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

# Log messages to Google Sheet
async def log_to_sheet(msg):
    try:
        sheet.append_row([
            msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            msg.author.name,
            msg.content
        ])
    except Exception as e:
        print("Error logging to sheet:", e)

# Oil Summary Calculator
def calculate_oil_summary(messages):
    total_taken = 0
    for i in range(len(messages) - 1):
        try:
            after = float(messages[i].content.split("Oil stock after :")[1].strip())
            before = float(messages[i + 1].content.split("Oil stock before :")[1].strip())
            diff = before - after
            if diff > 0:
                total_taken += diff
        except:
            continue
    return total_taken

# Trip Summary Calculator
def calculate_trip_summary(messages):
    trip_counts = {}
    for msg in messages:
        author = msg.author.name
        if "Trip" in msg.content:
            trip_counts[author] = trip_counts.get(author, 0) + 1
    return trip_counts

# Daily Summary Auto Task
@tasks.loop(time=dtime(hour=18, minute=00, tzinfo=pytz.timezone("Asia/Kolkata")))
async def daily_oil_summary():
    channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    report_channel = bot.get_channel(REPORT_CHANNEL_ID)
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    yesterday = now - timedelta(days=1)

    messages = []
    async for msg in channel.history(after=yesterday, before=now, limit=None):
        messages.append(msg)
        await log_to_sheet(msg)

    messages = sorted(messages, key=lambda m: m.created_at, reverse=True)
    oil_taken = calculate_oil_summary(messages)
    await report_channel.send(f"**Daily Oil Summary (last 24 hrs)**:\nTotal Oil Taken: {oil_taken}L")

# Command-based oil summary
@bot.command()
async def oil_summary(ctx, start: str, end: str):
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        messages = [msg async for msg in channel.history(after=start_time, before=end_time)]
        messages = sorted(messages, key=lambda m: m.created_at, reverse=True)
        oil_taken = calculate_oil_summary(messages)
        await ctx.send(f"**Oil Summary:**\nFrom {start} to {end}\nTotal Oil Taken: {oil_taken}L")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Command-based trip summary
@bot.command()
async def trip_summary(ctx, start: str, end: str):
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        messages = [msg async for msg in channel.history(after=start_time, before=end_time)]
        trip_counts = calculate_trip_summary(messages)
        if trip_counts:
            result = "\n".join(f"{k}: {v} trips" for k, v in trip_counts.items())
        else:
            result = "No trips found."
        await ctx.send(f"**Trip Summary:**\nFrom {start} to {end}\n{result}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    daily_oil_summary.start()

@bot.event
async def on_message(message):
    if message.channel.id == OIL_LOG_CHANNEL_ID and not message.author.bot:
        await log_to_sheet(message)
    await bot.process_commands(message)

# Run the bot
bot.run(TOKEN)
