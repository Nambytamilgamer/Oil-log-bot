import discord
from discord.ext import commands
import re
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

oil_logs = []

before_pattern = re.compile(r"before[:\-]?\s*(\d+)", re.IGNORECASE)
after_pattern = re.compile(r"after[:\-]?\s*(\d+)", re.IGNORECASE)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content
    before_match = before_pattern.search(content)
    after_match = after_pattern.search(content)

    if before_match and after_match:
        before = int(before_match.group(1))
        after = int(after_match.group(1))
        oil_taken = before - after

        oil_logs.append({
            "timestamp": message.created_at.isoformat(),
            "before": before,
            "after": after,
            "taken": oil_taken
        })

        await message.channel.send(
            f"Oil log recorded.\nBefore: {before}L\nAfter: {after}L\nOil taken: {oil_taken}L"
        )

    await bot.process_commands(message)

@bot.command()
async def show_logs(ctx):
    if not oil_logs:
        await ctx.send("No logs recorded yet.")
        return

    msg = "**Oil Logs:**\n"
    for log in oil_logs[-5:]:
        msg += f"{log['timestamp']} - Taken: {log['taken']}L (Before: {log['before']}, After: {log['after']})\n"

    await ctx.send(msg)

bot.run(os.environ['TOKEN'])
