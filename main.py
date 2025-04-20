import discord
from discord.ext import commands, tasks
import re
import os
import json
from datetime import datetime, timedelta
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Updated channel IDs
LOG_CHANNEL_ID = 1347225637949149285     # Employees log oil data here
REPORT_CHANNEL_ID = 1347192193453916171  # Bot sends summaries here
SUMMARY_HOUR_IST = 18  # Time bot sends auto daily summary

# --- Google Sheet Setup ---
def get_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1
    return sheet

# --- Regex for message parsing ---
before_pattern = re.compile(r"before\s*[:\-]?\s*(\d+)", re.IGNORECASE)
after_pattern = re.compile(r"after\s*[:\-]?\s*(\d+)", re.IGNORECASE)
trip_pattern = re.compile(r"trip\s*(\d+)", re.IGNORECASE)

def extract_oil_data(content):
    before = before_pattern.search(content)
    after = after_pattern.search(content)
    trip = trip_pattern.search(content)
    if before and after:
        return int(before.group(1)), int(after.group(1)), int(trip.group(1)) if trip else None
    return None

# --- Events ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    daily_summary.start()

@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != LOG_CHANNEL_ID:
        return

    oil_data = extract_oil_data(message.content)
    if oil_data:
        before, after, trip_no = oil_data
        sheet = get_gsheet()
        sheet.append_row([
            message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            message.author.name,
            trip_no if trip_no is not None else "",
            before,
            after
        ])
    await bot.process_commands(message)

# --- Commands ---
@bot.command()
async def oil_summary(ctx, start_time: str, end_time: str):
    await send_summary(ctx.channel, start_time, end_time)

@bot.command()
async def trip_summary(ctx):
    ist = pytz.timezone("Asia/Kolkata")
    since = datetime.now(ist) - timedelta(days=7)
    sheet = get_gsheet()
    data = sheet.get_all_records()
    counts = defaultdict(int)

    for row in data:
        ts_str = row['Timestamp']
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").astimezone(ist)
            if ts >= since and row['Trip No']:
                counts[row['Employee']] += 1
        except:
            continue

    if not counts:
        await ctx.send("No trips recorded in the last 7 days.")
        return

    summary = "\n".join([f"{name}: {count} trips" for name, count in counts.items()])
    await ctx.send(f"**🧾 Trip Summary (Last 7 Days)**\n{summary}")

# --- Summary Function ---
async def send_summary(channel, start_time_str, end_time_str):
    try:
        ist = pytz.timezone("Asia/Kolkata")
        start = datetime.fromisoformat(start_time_str).astimezone(ist)
        end = datetime.fromisoformat(end_time_str).astimezone(ist)
    except ValueError:
        await channel.send("❌ Invalid datetime format!\nUse: `YYYY-MM-DDTHH:MM+05:30`")
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            before, after, _ = oil_data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "timestamp": msg.created_at
            })

    messages.sort(key=lambda x: x["timestamp"])
    total_taken = 0
    trip_logs = []

    for i in range(len(messages) - 1):
        current = messages[i]
        next_msg = messages[i + 1]
        oil_taken = current["after"] - next_msg["before"]
        if oil_taken > 0:
            total_taken += oil_taken
            trip_logs.append(f"Trip {i+1} by {current['author']}: {current['after']} → {next_msg['before']} = {oil_taken}L")

    if not trip_logs:
        await channel.send("No valid oil movement in the given time frame.")
    else:
        summary = "\n".join(trip_logs)
        await channel.send(
            f"**🛢 OIL SUMMARY**\nFrom `{start.strftime('%d-%m-%Y %H:%M')}` to `{end.strftime('%d-%m-%Y %H:%M')}`\n\n"
            f"{summary}\n\n**Total Oil Taken: {total_taken} L**"
        )

# --- Daily Auto Summary ---
@tasks.loop(minutes=1)
async def daily_summary():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    if now.hour == SUMMARY_HOUR_IST and now.minute == 0:
        report_channel = bot.get_channel(REPORT_CHANNEL_ID)
        if report_channel:
            end = now
            start = end - timedelta(days=1)
            await send_summary(report_channel, start.isoformat(), end.isoformat())

# --- Start Bot ---
if __name__ == "__main__":
    import asyncio

    async def start_bot():
        await bot.start(os.getenv("TOKEN"))

    asyncio.run(start_bot())
