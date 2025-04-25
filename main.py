import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dtime
import pytz
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from fpdf import FPDF

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
    messages = sorted(messages, key=lambda m: m.created_at)  # Sort oldest to newest

    for i in range(len(messages) - 1):
        try:
            before_msg = messages[i]
            after_msg = messages[i + 1]

            before = float(before_msg.content.split("Oil stock before :")[1].split("Oil stock after :")[0].strip())
            after = float(after_msg.content.split("Oil stock after :")[1].strip())

            diff = before - after
            if diff > 0:
                total_taken += diff
        except Exception as e:
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

    messages = sorted(messages, key=lambda m: m.created_at)
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

@bot.command()
async def bonus_summary(ctx, start: str, end: str):
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        messages = [msg async for msg in channel.history(after=start_time, before=end_time)]
        trip_counts = calculate_trip_summary(messages)

        if not trip_counts:
            await ctx.send("No trips found in the given time range.")
            return

        bonus_msg = ""
        total_bonus = 0
        for person, trips in trip_counts.items():
            bonus = trips * 288000
            total_bonus += bonus
            bonus_msg += f"{person}: {trips} trips × ₹288000 = ₹{bonus}\n"

        bonus_msg += f"\n**Total Bonus Payout: ₹{total_bonus}**"
        await ctx.send(f"**Bonus Summary:**\nFrom {start} to {end}\n{bonus_msg}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command()
async def final_calc(ctx, start: str, end: str):
    try:
        # Parse times
        start_dt = datetime.fromisoformat(start)
        end_dt   = datetime.fromisoformat(end)
        channel  = bot.get_channel(OIL_LOG_CHANNEL_ID)

        # Fetch & sort messages
        msgs = [m async for m in channel.history(after=start_dt, before=end_dt, limit=None)]
        msgs.sort(key=lambda m: m.created_at)

        # Compute trip counts & oil moved
        trip_counts  = calculate_trip_summary(msgs)
        total_trips  = sum(trip_counts.values())
        trip_value   = total_trips * 640_000

        total_oil    = calculate_oil_summary(msgs)
        oil_value    = (total_oil / 3000) * 480_000

        total_amount    = trip_value + oil_value
        bonus_total     = total_trips * 288_000
        remaining       = total_amount - bonus_total
        forty_percent   = remaining * 0.4

        # Build PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Final Calculation Report", ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 8, f"Period: {start} to {end}", ln=True)
        pdf.ln(5)

        pdf.cell(0, 8, "Trip Summary:", ln=True)
        for user, cnt in trip_counts.items():
            pdf.cell(0, 8, f"  • {user}: {cnt} trips → ₹{cnt * 288_000}", ln=True)
        pdf.ln(5)

        pdf.cell(0, 8, f"Total Trips: {total_trips} → ₹{trip_value}", ln=True)
        pdf.cell(0, 8, f"Total Oil Taken: {total_oil} L → Value: ₹{oil_value:.2f}", ln=True)
        pdf.cell(0, 8, f"Combined Amount: ₹{total_amount:.2f}", ln=True)
        pdf.cell(0, 8, f"Total Bonus Deducted: ₹{bonus_total}", ln=True)
        pdf.cell(0, 8, f"Remaining Amount: ₹{remaining:.2f}", ln=True)
        pdf.cell(0, 8, f"40% of Remaining: ₹{forty_percent:.2f}", ln=True)

        # Output to Discord DM
        buffer = BytesIO()
        pdf.output(buffer)
        buffer.seek(0)
        file = discord.File(fp=buffer, filename="final_report.pdf")
        dm = await ctx.author.create_dm()
        await dm.send("Here’s your final calculation report:", file=file)

        # Optional: confirm in channel
        await ctx.send(f"{ctx.author.mention}, I’ve DM’d you the PDF report!")

    except Exception as e:
        await ctx.send(f"❌ Error in final_calc: {e}")
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
