import os
import discord
import asyncio
import pytz
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re
import json
from dateutil import parser as dtparser

# ENV VARS
TOKEN = os.environ['TOKEN']
GOOGLE_SHEET_ID = os.environ['GOOGLE_SHEET_ID']
GOOGLE_CREDS_JSON = json.loads(os.environ['GOOGLE_CREDS_JSON'])

# CHANNELS
LOG_CHANNEL_ID = 1347225637949149285
REPORT_CHANNEL_ID = 1347192193453916171

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Google Sheets Setup
creds = service_account.Credentials.from_service_account_info(
    GOOGLE_CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

SHEET_RANGE = "Sheet1!A:F"

# Utils
def get_logs_from_sheet():
    result = sheet.values().get(spreadsheetId=GOOGLE_SHEET_ID, range=SHEET_RANGE).execute()
    values = result.get('values', [])
    return values[1:] if len(values) > 1 else []

def append_log_to_sheet(log_data):
    sheet.values().append(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=SHEET_RANGE,
        valueInputOption="RAW",
        body={"values": [log_data]}
    ).execute()

def extract_log_data(message):
    content = message.content
    match = re.search(r"Trip\s*:? ?(\d+)[\s\S]*?Date\s*:? ?([\d-]+)[\s\S]*?Oil stock before\s*:? ?(\d+)[\s\S]*?Oil stock after\s*:? ?(\d+)", content)
    if match:
        trip = match.group(1)
        date = match.group(2)
        before = int(match.group(3))
        after = int(match.group(4))
        return [message.created_at.isoformat(), str(message.author), trip, date, before, after]
    return None

def calculate_oil(logs):
    total = 0
    for i in range(len(logs) - 1):
        try:
            after1 = int(logs[i][5])
            before2 = int(logs[i+1][4])
            if after1 != before2:
                total += abs(before2 - after1)
        except:
            continue
    return total

def calculate_trips(logs):
    trips = {}
    for row in logs:
        user = row[1]
        trips[user] = trips.get(user, 0) + 1
    return trips

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    daily_summary.start()

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id == LOG_CHANNEL_ID and not message.author.bot:
        logs = get_logs_from_sheet()
        last_logged_time = datetime.min
        if logs:
            try:
                last_logged_time = dtparser.parse(logs[-1][0])
            except:
                pass

        if message.created_at > last_logged_time:
            data = extract_log_data(message)
            if data:
                append_log_to_sheet(data)

@tasks.loop(minutes=1)
async def daily_summary():
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    if now.hour == 18 and now.minute == 0:
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        messages = [m async for m in log_channel.history(limit=1000)]
        messages.reverse()

        valid_logs = [extract_log_data(m) for m in messages if extract_log_data(m)]
        oil_moved = calculate_oil(valid_logs)
        trips = calculate_trips(valid_logs)

        report = f"**Daily Oil Summary - {now.strftime('%Y-%m-%d')}**\nTotal Oil Moved: {oil_moved}L\n\n**Trip Count:**\n"
        for user, count in trips.items():
            report += f"{user}: {count} trips\n"

        report_channel = bot.get_channel(REPORT_CHANNEL_ID)
        await report_channel.send(report)

@bot.command()
async def oil_summary(ctx, start: str, end: str):
    try:
        start_dt = dtparser.parse(start)
        end_dt = dtparser.parse(end)
    except Exception as e:
        await ctx.send(f"Invalid date format: {e}")
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    messages = [m async for m in log_channel.history(limit=1000)]
    messages = [m for m in messages if start_dt <= m.created_at <= end_dt]
    messages.sort(key=lambda m: m.created_at)

    logs = [extract_log_data(m) for m in messages if extract_log_data(m)]
    oil_moved = calculate_oil(logs)
    await ctx.send(f"**Oil Summary from {start} to {end}**\nTotal Oil Moved: {oil_moved}L")

@bot.command()
async def trip_summary(ctx, start: str, end: str):
    try:
        start_dt = dtparser.parse(start)
        end_dt = dtparser.parse(end)
    except Exception as e:
        await ctx.send(f"Invalid date format: {e}")
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    messages = [m async for m in log_channel.history(limit=1000)]
    messages = [m for m in messages if start_dt <= m.created_at <= end_dt]
    messages.sort(key=lambda m: m.created_at)

    logs = [extract_log_data(m) for m in messages if extract_log_data(m)]
    trips = calculate_trips(logs)

    report = f"**Trip Summary from {start} to {end}**\n"
    for user, count in trips.items():
        report += f"{user}: {count} trips\n"
    await ctx.send(report)

bot.run(TOKEN)

