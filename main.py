import discord
from discord.ext import commands
import re
import os
from datetime import datetime
import pytz

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Regex to match oil before and after
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

@bot.command()
async def oil_summary(ctx, start_time: str, end_time: str):
    try:
        ist = pytz.timezone("Asia/Kolkata")
        start = datetime.fromisoformat(start_time).astimezone(ist)
        end = datetime.fromisoformat(end_time).astimezone(ist)
    except ValueError:
        await ctx.send("Invalid datetime format! Use `YYYY-MM-DDTHH:MM+05:30`")
        return

    messages = []
    async for msg in ctx.channel.history(after=start, before=end, limit=None):
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

    messages.sort(key=lambda x: x["timestamp"])  # sort chronologically

    total_taken = 0
    trip_logs = []

    for i in range(len(messages) - 1):
        current = messages[i]
        next_msg = messages[i + 1]

        oil_taken = current["after"] - next_msg["before"]
        if oil_taken > 0:
            total_taken += oil_taken
            trip_logs.append(
                f"Trip {i+1}: {current['after']} → {next_msg['before']} = {oil_taken}L"
            )

    if not trip_logs:
        await ctx.send("No valid oil logs or no oil movement found in the time frame.")
    else:
        summary = "\n".join(trip_logs)
        await ctx.send(
            f"**OIL SUMMARY** from {start.strftime('%d-%m-%Y %H:%M')} to {end.strftime('%d-%m-%Y %H:%M')}\n\n"
            f"{summary}\n\n**Total Oil Taken: {total_taken} L**"
        )

bot.run(os.environ["TOKEN"])
