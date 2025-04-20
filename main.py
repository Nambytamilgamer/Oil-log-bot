import discord
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta, time
import pytz
import json
import gspread
from collections import defaultdict

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Channel IDs (hardcoded)
OIL_LOG_CHANNEL_ID = 1347225637949149285  # Employees post logs here
REPORT_CHANNEL_ID = 1347192193453916171   # Daily summary posted here

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Google Sheet Setup
gc = gspread.service_account_from_dict(json.loads(os.getenv("GOOGLE_CREDS_JSON")))
sheet = gc.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
worksheet = sheet.sheet1


def extract_oil_data(message):
    try:
        lines = message.split('\n')
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


@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    daily_summary.start()


def calculate_oil_taken(entries):
    entries.sort(key=lambda x: x["timestamp"])
    total_taken = 0
    for i in range(len(entries) - 1):
        current_after = entries[i]["after"]
        next_before = entries[i + 1]["before"]
        if next_before < current_after:
            taken = current_after - next_before
            total_taken += taken
    return total_taken


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
            await ctx.send("❌ Invalid datetime format! Use `YYYY-MM-DDTHH:MM+05:30`")
            return

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    if log_channel is None:
        await ctx.send("❌ Could not find the log channel.")
        return

    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            before, after, trip_no = oil_data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "timestamp": msg.created_at
            })

    if not messages:
        await ctx.send("❌ No oil logs found in the specified time frame.")
        return

    total_taken = calculate_oil_taken(messages)

    await ctx.send(
        f"**🛢️ Oil Summary**\nFrom `{start.strftime('%d-%m-%Y %H:%M')}` to `{end.strftime('%d-%m-%Y %H:%M')}`\n"
        f"Total Oil Taken by Others: `{total_taken}` litres"
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
            await ctx.send("❌ Invalid datetime format! Use `YYYY-MM-DDTHH:MM+05:30`")
            return

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    if log_channel is None:
        await ctx.send("❌ Could not find the log channel.")
        return

    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        trip_no = None
        if oil_data:
            _, _, trip_no = oil_data
        if trip_no:
            messages.append({
                "author": msg.author.name,
                "trip_no": trip_no,
                "timestamp": msg.created_at
            })

    if not messages:
        await ctx.send("❌ No trips recorded in the specified time frame.")
        return

    messages.sort(key=lambda x: x["timestamp"])
    trip_counts = defaultdict(int)
    for msg in messages:
        trip_counts[msg['author']] += 1

    summary = "\n".join([f"{employee}: {count} trips" for employee, count in trip_counts.items()])
    await ctx.send(f"**🧾 Trip Summary**\nFrom `{start.strftime('%d-%m-%Y %H:%M')}` to `{end.strftime('%d-%m-%Y %H:%M')}`\n\n{summary}")


@tasks.loop(time=time(hour=18, minute=0, tzinfo=IST))
async def daily_summary():
    now = datetime.now(IST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    log_channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    report_channel = bot.get_channel(REPORT_CHANNEL_ID)

    messages = []
    async for msg in log_channel.history(after=start, before=end, limit=None):
        if msg.author.bot:
            continue
        oil_data = extract_oil_data(msg.content)
        if oil_data:
            before, after, trip_no = oil_data
            messages.append({
                "author": msg.author.name,
                "before": before,
                "after": after,
                "trip_no": trip_no,
                "timestamp": msg.created_at
            })

    if not messages:
        await report_channel.send("No oil data logged today.")
        return

    total_taken = calculate_oil_taken(messages)

    # Log to Google Sheets
    for entry in messages:
        worksheet.append_row([
            entry["author"],
            entry["trip_no"],
            entry["before"],
            entry["after"],
            entry["timestamp"].astimezone(IST).strftime("%d-%m-%Y %H:%M")
        ])

    await report_channel.send(
        f"📊 **Daily Oil Summary**\nDate: `{now.strftime('%d-%m-%Y')}`\nTotal Oil Taken: `{total_taken}` litres"
    )


bot.run(os.getenv("TOKEN"))

