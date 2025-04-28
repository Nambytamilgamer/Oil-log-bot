import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dtime
import pytz
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from discord import File

# ENV variables
TOKEN = os.getenv("TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = json.loads(os.getenv("GOOGLE_CREDS_JSON"))

# IDs
OIL_LOG_CHANNEL_ID = 1347225637949149285
REPORT_CHANNEL_ID = 1347192193453916171
ALLOWED_USER_IDS = {964098780557373550, 490600486794166308}  # <-- your ID + your friend's

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Google Sheet setup
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDS_JSON, scope)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

# Helper - check user
def is_allowed(ctx):
    return ctx.author.id in ALLOWED_USER_IDS

# Log to Google Sheet
async def log_to_sheet(msg):
    try:
        sheet.append_row([
            msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            msg.author.name,
            msg.content
        ])
    except Exception as e:
        print("Error logging to sheet:", e)

# Parse oil stocks and calculate total taken
def calculate_oil_summary(messages):
    total_taken = 0
    messages = sorted(messages, key=lambda m: m.created_at)

    stocks = []
    for msg in messages:
        try:
            before_match = re.search(r"oil stock before:\s*([0-9]+)", msg.content, re.IGNORECASE)
            after_match = re.search(r"oil stock after:\s*([0-9]+)", msg.content, re.IGNORECASE)

            if before_match and after_match:
                before = int(before_match.group(1))
                after = int(after_match.group(1))
                stocks.append({'before': before, 'after': after})
        except Exception as e:
            print(f"Error parsing oil stock: {e}")
            continue

    for i in range(len(stocks) - 1):
        after_current = stocks[i]['after']
        before_next = stocks[i + 1]['before']
        diff = after_current - before_next
        if diff > 0:
            total_taken += diff

    return total_taken

# Calculate trips
def calculate_trip_summary(messages):
    trip_counts = {}
    for msg in messages:
        if "Trip" in msg.content:
            trip_counts[msg.author.name] = trip_counts.get(msg.author.name, 0) + 1
    return trip_counts

# Daily oil summary task
@tasks.loop(time=dtime(hour=18, minute=00, tzinfo=pytz.timezone("Asia/Kolkata")))
async def daily_oil_summary():
    channel = bot.get_channel(OIL_LOG_CHANNEL_ID)
    report_channel = bot.get_channel(REPORT_CHANNEL_ID)
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    yesterday = now - timedelta(days=1)

    messages = [msg async for msg in channel.history(after=yesterday, before=now, limit=None)]
    for msg in messages:
        await log_to_sheet(msg)

    oil_taken = calculate_oil_summary(messages)
    await report_channel.send(f"**Daily Oil Summary (last 24 hrs)**:\nTotal Oil Taken: {oil_taken} L")

# --- Commands ---
@bot.command()
async def oil_summary(ctx, start: str, end: str):
    if not is_allowed(ctx):
        await ctx.send("🚫 Sorry, you don't have permission to use this command.")
        return
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        # Fetch messages
        messages = [msg async for msg in channel.history(after=start_time, before=end_time, limit=None)]
        messages = sorted(messages, key=lambda m: m.created_at)

        # Logging new messages to sheet
        existing_logs = sheet.col_values(1)
        for msg in messages:
            msg_timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            if msg_timestamp not in existing_logs:
                await log_to_sheet(msg)

        # Correct oil calculation (same as daily summary)
        total_oil = 0
        for i in range(len(messages) - 1):
            try:
                after = float(messages[i].content.lower().split("oil stock after:")[1].split("\n")[0].strip())
                before = float(messages[i+1].content.lower().split("oil stock before:")[1].split("\n")[0].strip())
                diff = before - after
                if diff > 0:
                    total_oil += diff
            except Exception as e:
                print(f"Skipping error during oil calculation: {e}")
                continue

        # Create Embed
        embed = discord.Embed(
            title="🛢️ Oil Summary Report",
            description=f"**Date Range:**\n`{start}` ➔ `{end}`",
            color=discord.Color.blue()
        )
        embed.add_field(name="Total Oil Taken", value=f"**{total_oil} Liters**", inline=False)
        embed.set_footer(text="Requested by " + ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command()
async def trip_summary(ctx, start: str, end: str):
    if not is_allowed(ctx):
        await ctx.send("🚫 Sorry, you don't have permission to use this command.")
        return
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
    if not is_allowed(ctx):
        await ctx.send("🚫 Sorry, you don't have permission to use this command.")
        return
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
    if not is_allowed(ctx):
        await ctx.send("🚫 Sorry, you don't have permission to use this command.")
        return
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        channel = bot.get_channel(OIL_LOG_CHANNEL_ID)

        messages = [msg async for msg in channel.history(after=start_time, before=end_time)]
        messages = sorted(messages, key=lambda m: m.created_at)

        # Calculate trip counts
        trip_counts = {}
        for msg in messages:
            author = msg.author.name
            if "Trip" in msg.content:
                trip_counts[author] = trip_counts.get(author, 0) + 1

        # Calculate total oil taken
        total_oil = 0
        for i in range(len(messages) - 1):
            try:
                after = float(messages[i].content.lower().split("oil stock after:")[1].split("\n")[0].strip())
                before = float(messages[i+1].content.lower().split("oil stock before:")[1].split("\n")[0].strip())
                diff = before - after
                if diff > 0:
                    total_oil += diff
            except Exception as e:
                print(f"Skipping error during oil calculation: {e}")
                continue

        # Calculations
        total_trips = sum(trip_counts.values())
        total_trip_amount = total_trips * 640000

        member_bonuses = {k: v * 288000 for k, v in trip_counts.items()}
        total_bonus_amount = sum(member_bonuses.values())

        oil_bill_amount = (total_oil / 3000) * 480000
        grand_total = total_trip_amount + oil_bill_amount

        after_bonus_total = grand_total - total_bonus_amount

        # Shares calculation
        jyothika_share = after_bonus_total * 0.40
        market_share = after_bonus_total * 0.30
        raja_rathinam_share = after_bonus_total * 0.20
        company_community_share = after_bonus_total * 0.10

        # Create PDF
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from discord import File

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        y = height - 50
        p.setFont("Helvetica-Bold", 18)
        p.drawString(200, y, "Final Calculation Report")
        y -= 40

        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Trip Counts:")
        y -= 25

        p.setFont("Helvetica", 12)
        for member, trips in trip_counts.items():
            p.drawString(60, y, f"{member}: {trips} trips")
            y -= 20

        y -= 20
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Bonus Amounts:")
        y -= 25

        p.setFont("Helvetica", 12)
        for member, bonus in member_bonuses.items():
            p.drawString(60, y, f"{member}: {bonus:,} units")
            y -= 20

        y -= 20
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Summary:")
        y -= 25

        p.setFont("Helvetica", 12)
        p.drawString(60, y, f"Total Oil Taken: {total_oil} Liters")
        y -= 20
        p.drawString(60, y, f"Total Trips: {total_trips}")
        y -= 20
        p.drawString(60, y, f"Trip Amount (640k/trip): {total_trip_amount:,} units")
        y -= 20
        p.drawString(60, y, f"Oil Bill Amount: {oil_bill_amount:,.2f} units")
        y -= 20
        p.drawString(60, y, f"Grand Total: {grand_total:,.2f} units")
        y -= 20
        p.drawString(60, y, f"Total Bonus Amount: {total_bonus_amount:,} units")
        y -= 20
        p.drawString(60, y, f"After Bonus Deduction: {after_bonus_total:,.2f} units")
        y -= 20

        y -= 20
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Shares Distribution:")
        y -= 25

        p.setFont("Helvetica", 12)
        p.drawString(60, y, f"Jyothika (40%): ₹{jyothika_share:,.2f}")
        y -= 20
        p.drawString(60, y, f"Market (30%): ₹{market_share:,.2f}")
        y -= 20
        p.drawString(60, y, f"Raja Rathinam (20%): ₹{raja_rathinam_share:,.2f}")
        y -= 20
        p.drawString(60, y, f"Company & Community Needs (10%): ₹{company_community_share:,.2f}")

        p.showPage()
        p.save()
        buffer.seek(0)

        # Send the PDF as DM
        await ctx.author.send(file=File(buffer, filename="final_report.pdf"))
        await ctx.send("✅ Final calculation report sent to your DM!")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
# Events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    daily_oil_summary.start()

@bot.event
async def on_message(message):
    if message.channel.id == OIL_LOG_CHANNEL_ID and not message.author.bot:
        await log_to_sheet(message)
    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    if after.channel.id == OIL_LOG_CHANNEL_ID and not after.author.bot:
        try:
            cell = sheet.find(before.created_at.strftime('%Y-%m-%d %H:%M:%S'))
            if cell:
                sheet.update_cell(cell.row, 2, after.author.name)
                sheet.update_cell(cell.row, 3, after.content)
        except Exception as e:
            print("Error updating sheet for edited message:", e)

# Run the bot
bot.run(TOKEN)
