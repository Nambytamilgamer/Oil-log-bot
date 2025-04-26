import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dtime
import pytz
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
            bonus_msg += f"{person}: {trips} trips Ã— â‚¹288000 = â‚¹{bonus}\n"

        bonus_msg += f"\n**Total Bonus Payout: â‚¹{total_bonus}**"
        await ctx.send(f"**Bonus Summary:**\nFrom {start} to {end}\n{bonus_msg}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


from fpdf import FPDF

@bot.command()
async def final_calc(ctx, start: str, end: str):
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        messages = [msg async for msg in channel.history(after=start_time, before=end_time)]
        messages = sorted(messages, key=lambda m: m.created_at, reverse=True)

        oil_taken = calculate_oil_summary(messages)
        trip_counts = calculate_trip_summary(messages)

        # Calculations
        total_trips = sum(trip_counts.values())
        trip_bonus = total_trips * 640000
        oil_bonus = (oil_taken / 3000) * 480000
        total_amount = trip_bonus + oil_bonus
        bonus_deducted_amount = total_amount - trip_bonus
        share_40_percent = (bonus_deducted_amount) * 0.4

        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(200, 10, txt="Final Oil and Trip Calculation Report", ln=True, align='C')
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"From {start} to {end}", ln=True, align='L')
        pdf.ln(10)

        pdf.cell(200, 10, txt="Trip Counts:", ln=True, align='L')
        for member, trips in trip_counts.items():
            pdf.cell(200, 10, txt=f"{member}: {trips} trips", ln=True, align='L')

        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Total Trips: {total_trips}", ln=True, align='L')
        pdf.cell(200, 10, txt=f"Total Oil Taken: {oil_taken}L", ln=True, align='L')
        pdf.ln(10)

        pdf.cell(200, 10, txt=f"Trip Bonus (640000 per trip): {trip_bonus:,} ₹", ln=True, align='L')
        pdf.cell(200, 10, txt=f"Oil Bonus (480000 per 3000L): {oil_bonus:,.2f} ₹", ln=True, align='L')
        pdf.cell(200, 10, txt=f"Total Bonus Amount: {total_amount:,.2f} ₹", ln=True, align='L')
        pdf.cell(200, 10, txt=f"After Trip Bonus Deduction: {bonus_deducted_amount:,.2f} ₹", ln=True, align='L')
        pdf.cell(200, 10, txt=f"40% Share Amount: {share_40_percent:,.2f} ₹", ln=True, align='L')

        # Save and send
        output_file = f"/tmp/final_calc_{ctx.author.id}.pdf"
        pdf.output(output_file)

        await ctx.author.send(file=discord.File(output_file))
        await ctx.send(f"✅ Final calculation completed! Report sent to your DM, {ctx.author.mention}")
        
    except Exception as e:
        await ctx.send(f"Error: {e}")

        
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
