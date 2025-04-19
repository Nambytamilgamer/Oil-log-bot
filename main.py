import discord
from discord.ext import commands
import re
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Updated regex to support "Oil stock before/after"
before_pattern = re.compile(r"(?:oil stock\s*)?before[:\-]?\s*(\d+)", re.IGNORECASE)
after_pattern = re.compile(r"(?:oil stock\s*)?after[:\-]?\s*(\d+)", re.IGNORECASE)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

def extract_oil_data(content):
    content = content.lower().replace(",", "")  # Optional cleanup
    before_match = before_pattern.search(content)
    after_match = after_pattern.search(content)
    if before_match and after_match:
        before = int(before_match.group(1))
        after = int(after_match.group(1))
        taken = before - after
        return before, after, taken
    return None

@bot.command()
async def oil_summary(ctx, start_time: str, end_time: str):
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
    except ValueError:
        await ctx.send("Invalid datetime format! Use YYYY-MM-DDTHH:MM (e.g. 2025-04-18T14:30)")
        return

    total_taken = 0
    log_count = 0

    async for msg in ctx.channel.history(after=start, before=end, limit=None):
        if msg.author.id == bot.user.id:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            _, _, taken = oil_data
            total_taken += taken
            log_count += 1

    if log_count == 0:
        await ctx.send("No oil logs found in that time frame.")
    else:
        await ctx.send(
            f"From **{start_time}** to **{end_time}**:\n"
            f"Logs found: {log_count}\n"
            f"Total oil taken: **{total_taken}L**"
        )

bot.run(os.environ['TOKEN'])
