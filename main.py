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

DEBUG = True  # Change to False to disable debug messages in Discord

# Updated regex to match various formats
before_pattern = re.compile(r"(?:oil\s*stock\s*)?before[:\-]?\s*(\d+)", re.IGNORECASE)
after_pattern = re.compile(r"(?:oil\s*stock\s*)?after[:\-]?\s*(\d+)", re.IGNORECASE)

def extract_oil_data(content):
    content = content.lower().replace(",", "")  # Sanitize
    before_match = before_pattern.search(content)
    after_match = after_pattern.search(content)
    if before_match and after_match:
        before = int(before_match.group(1))
        after = int(after_match.group(1))
        return before, after
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
        await ctx.send("Invalid datetime format! Use `YYYY-MM-DDTHH:MM+05:30` (e.g. `2025-04-19T08:00+05:30`)")
        return

    total_taken = 0
    log_count = 0
    logs = []
    previous_after = None

    async for msg in ctx.channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            before, after = oil_data
            if previous_after is not None:
                taken = previous_after - before
                if taken > 0:  # Only count if there's a positive difference
                    log_count += 1
                    total_taken += taken
                    logs.append((msg.author.name, taken, previous_after, before, msg.created_at.strftime("%Y-%m-%d %H:%M:%S")))
                    if DEBUG:
                        await ctx.send(f"**{msg.author.name}**: Taken = {taken}L (from {previous_after} → {before})")
            previous_after = after  # Update previous "after" for next comparison

    if log_count == 0:
        await ctx.send("No valid oil logs found in that time frame.")
    else:
        await ctx.send(
            f"\n**OIL SUMMARY** from **{start.strftime('%Y-%m-%d %H:%M')}** to **{end.strftime('%Y-%m-%d %H:%M')}**:\n"
            f"Logs Found: {log_count}\n"
            f"Total Oil Taken: **{total_taken}L**"
        )

bot.run(os.environ['TOKEN'])
