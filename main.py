import discord
from discord.ext import commands, tasks
import re
import os
from datetime import datetime, timedelta
import pytz

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

CHANNEL_ID = 1347192193453916171  # Replace with your oil log channel ID
SUMMARY_HOUR_IST = 18  # 6 PM IST

# Regex patterns
before_pattern = re.compile(r"before\s*[:\-]?\s*(\d+)", re.IGNORECASE)
after_pattern = re.compile(r"after\s*[:\-]?\s*(\d+)", re.IGNORECASE)

def extract_oil_data(content):
    before = before_pattern.search(content)
    after = after_pattern.search(content)
    if before and after:
        return int(before.group(1)), int(after.group(1))
    return None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    daily_summary.start()  # Start the task when bot is ready

@bot.command()
async def oil_summary(ctx, start_time: str, end_time: str):
    await send_summary(ctx.channel, start_time, end_time)

async def send_summary(channel, start_time_str, end_time_str):
    try:
        ist = pytz.timezone("Asia/Kolkata")
        start = datetime.fromisoformat(start_time_str).astimezone(ist)
        end = datetime.fromisoformat(end_time_str).astimezone(ist)
    except ValueError:
        await channel.send("Invalid datetime format! Use `YYYY-MM-DDTHH:MM+05:30`")
        return

    messages = []
    async for msg in channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            before, after = oil_data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "timestamp": msg.created_at
            })

    messages.sort(key=lambda x: x["timestamp"])  # sort by time

    total_taken = 0
    trip_logs = []

    for i in range(len(messages) - 1):
        current = messages[i]
        next_msg = messages[i + 1]
        oil_taken = current["after"] - next_msg["before"]
        if oil_taken > 0:
            total_taken += oil_taken
            trip_logs.append(
                f"Trip {i+1} by {current['author']}: {current['after']} → {next_msg['before']} = {oil_taken}L"
            )

    if not trip_logs:
        await channel.send("No valid oil logs or no oil movement found in the time frame.")
    else:
        summary = "\n".join(trip_logs)
        await channel.send(
            f"**OIL SUMMARY** from {start.strftime('%d-%m-%Y %H:%M')} to {end.strftime('%d-%m-%Y %H:%M')}\n\n"
            f"{summary}\n\n**Total Oil Taken: {total_taken} L**"
        )

@tasks.loop(minutes=1)
async def daily_summary():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    if now.hour == SUMMARY_HOUR_IST and now.minute == 0:
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            end = now
            start = end - timedelta(days=1)
            await send_summary(channel, start.isoformat(), end.isoformat())

