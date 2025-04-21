import discord
from discord.ext import commands, tasks
import os
import json
import gspread
from datetime import datetime, timedelta, time
from collections import defaultdict
import pytz

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Channel IDs
OIL_LOG_CHANNEL_ID = 1347225637949149285
REPORT_CHANNEL_ID = 1347192193453916171

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Google Sheets setup
gc = gspread.service_account_from_dict(json.loads(os.getenv("GOOGLE_CREDS_JSON")))
sheet = gc.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
worksheet = sheet.sheet1


def extract_oil_data(content):
    try:
        lines = content.split('\n')
        trip_line = next((line for line in lines if "Trip" in line), "")
        date_line = next((line for line in lines if "Date" in line), "")
        before_line = next((line for line in lines if "before" in line), "")
        after_line = next((line for line in lines if "after" in line), "")

        trip_no = int(trip_line.split("Trip")[1].split(":")[0].strip())
        date = date_line.split(":")[1].strip()
        before = int(''.join(filter(str.isdigit, before_line)))
        after = int(''.join(filter(str.isdigit, after_line)))

        return before, after, trip_no
    except:
        return None


def calculate_oil_taken(entries):
    entries.sort(key=lambda x: x["timestamp"])
    total_taken = 0
    for i in range(len(entries) - 1):
        current_after = entries[i]["after"]
        next_before = entries[i + 1]["before"]
        if next_before < current_after:
            total_taken += current_after - next_before
    return total_taken


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    daily_summary.start()


@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot or message.channel.id != OIL_LOG_CHANNEL_ID:
        return

    oil_data = extract_oil_data(message.content)
    if oil_data:
        before, after, trip_no = oil_data
        worksheet.append_row([
            message.created_at.astimezone(IST).strftime("%d-%m-%Y %H:%M"),
            message.author.name,
            trip_no,
            before,
            after
        ])


@bot.command()
async def oil_summary(ctx, start_time: str = None, end_time: str = None):
    if not start_time or not end_time:
        end = datetime.now(IST)
        start = end - timedelta(days=1)
    else:
        try:
            start = datetime.fromisoformat(start_time).astimezone(IST)
            end = datetime.fromisoformat(end_time).astimezone(IST)
        except ValueError:
            await ctx.send("❌ Invalid format. Use: `YYYY-MM-DDTHH:MM+05:30`")
            return

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    if not log_channel:
        await ctx.send("❌ Log channel not found.")
        return

    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        data = extract_oil_data(msg.content)
        if data:
            before, after, _ = data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "timestamp": msg.created_at
            })

    if not messages:
        await ctx.send("No oil logs in this time frame.")
        return

    total_taken = calculate_oil_taken(messages)
    await ctx.send(
        f"**🛢️ Oil Summary**\nFrom `{start.strftime('%d-%m-%Y %H:%M')}` to `{end.strftime('%d-%m-%Y %H:%M')}`\n"
        f"Total Oil Taken: `{total_taken}` litres"
    )


@bot.command()
async def trip_summary(ctx, start_time: str = None, end_time: str = None):
    if not start_time or not end_time:
        end = datetime.now(IST)
        start = end - timedelta(days=7)
    else:
        try:
            start = datetime.fromisoformat(start_time).astimezone(IST)
            end = datetime.fromisoformat(end_time).astimezone(IST)
        except ValueError:
            await ctx.send("❌ Invalid format. Use: `YYYY-MM-DDTHH:MM+05:30`")
            return

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    if not log_channel:
        await ctx.send("❌ Log channel not found.")
        return

    trip_counts = defaultdict(int)
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        data = extract_oil_data(msg.content)
        if data:
            trip_counts[msg.author.name] += 1

    if not trip_counts:
        await ctx.send("No trips found in this time range.")
        return

    summary = "\n".join([f"{user}: {count} trips" for user, count in trip_counts.items()])
    await ctx.send(f"**🧾 Trip Summary**\nFrom `{start.strftime('%d-%m-%Y %H:%M')}` to `{end.strftime('%d-%m-%Y %H:%M')}`\n\n{summary}")


@tasks.loop(time=time(hour=18, tzinfo=IST))
async def daily_summary():
    now = datetime.now(IST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    report_channel = bot.get_channel(REPORT_CHANNEL_ID)

    if not log_channel or not report_channel:
        print("Channels not found.")
        return

    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        data = extract_oil_data(msg.content)
        if data:
            before, after, trip_no = data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "trip_no": trip_no,
                "timestamp": msg.created_at
            })

    if not messages:
        await report_channel.send("No oil logs today.")
        return

    total_taken = calculate_oil_taken(messages)

    for entry in messages:
        worksheet.append_row([
            entry["timestamp"].astimezone(IST).strftime("%d-%m-%Y %H:%M"),
            entry["author"],
            entry["trip_no"],
            entry["before"],
            entry["after"]
        ])

    await report_channel.send(
        f"📊 **Daily Oil Summary**\nDate: `{now.strftime('%d-%m-%Y')}`\nTotal Oil Taken: `{total_taken}` litres"
    )


bot.run(os.getenv("TOKEN"))
