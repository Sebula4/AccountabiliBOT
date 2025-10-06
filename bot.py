import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import json
import asyncio

# Constants
MAX_USERS = 20
DATA_FILE = "data/users.json"

# Discord setup
intents = discord.Intents.default()
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

# In-memory user data
user_data = {}

# ---------- File Handling ----------
def save_data():
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(user_data, f, indent=4)

def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            user_data = json.load(f)
    else:
        user_data = {}

# ---------- Bot Events ----------
@client.event
async def on_ready():
    load_data()
    await tree.sync()
    scheduler.start()
    print(f"Bot is online as {client.user}.")


# ---------- Slash Commands ----------

@tree.command(name="add_user", description="Add yourself to the accountability list.")
async def add_user(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id in user_data:
        await interaction.response.send_message("You're already on the list.", ephemeral=True)
        return

    if len(user_data) >= MAX_USERS:
        await interaction.response.send_message("User limit reached (20 users).", ephemeral=True)
        return

    user_data[user_id] = {
        "name": interaction.user.name,
        "goal": 3,
        "workouts": 0,
        "streak": 0
    }
    save_data()
    await interaction.response.send_message(f"{interaction.user.name} added to the accountability list!")

@tree.command(name="workout", description="Log a workout for this week.")
@app_commands.describe(description="Optional short description of your workout")
async def workout(interaction: discord.Interaction, description: str | None = None):
    user_id = str(interaction.user.id)

    if user_id not in user_data:
        await interaction.response.send_message("You're not on the list. Use `/add_user` to join.", ephemeral=True)
        return

    # Increment workout count
    user_data[user_id]["workouts"] += 1

    # Optionally store the description (add a simple log if desired)
    if description:
        # Optional: create a new field to store recent workouts
        if "recent_workouts" not in user_data[user_id]:
            user_data[user_id]["recent_workouts"] = []
        user_data[user_id]["recent_workouts"].append(description)

        # Keep only the last 5 workouts to limit data growth
        user_data[user_id]["recent_workouts"] = user_data[user_id]["recent_workouts"][-5:]

    save_data()

    # Construct response message
    message = f"💪 Great job! Workouts this week: {user_data[user_id]['workouts']}"
    if description:
        message += f"\n📝 You logged: *{description}*"

    await interaction.response.send_message(message)


@tree.command(name="set_goal", description="Set your workout goal per week.")
@app_commands.describe(goal="Your desired number of workouts per week")
async def set_goal(interaction: discord.Interaction, goal: int):
    user_id = str(interaction.user.id)

    if user_id not in user_data:
        await interaction.response.send_message("You're not on the list. Use `/add_user` to join.", ephemeral=True)
        return

    if goal < 1:
        await interaction.response.send_message("Goal must be at least 1.", ephemeral=True)
        return

    user_data[user_id]["goal"] = goal
    save_data()
    await interaction.response.send_message(f"Your goal has been set to {goal} workouts per week.")

@tree.command(name="display", description="Display everyone's stats.")
async def display(interaction: discord.Interaction):
    if not user_data:
        await interaction.response.send_message("No users are currently being tracked.")
        return

    embed = discord.Embed(title="🏋️ Accountability Stats", color=discord.Color.blue())
    for user in sorted(user_data.values(), key=lambda x: x["name"].lower()):
        embed.add_field(
            name=user["name"],
            value=f"Workouts: {user['workouts']} / {user['goal']}  |  🔥 Streak: {user['streak']}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@tree.command(name="set_streak", description="Adjust a user's current workout streak (admin only).")
@app_commands.describe(
    user="The user whose streak you want to adjust",
    streak="The new streak value (must be 0 or higher)"
)
async def set_streak(interaction: discord.Interaction, user: discord.User, streak: int):

    user_id = str(user.id)

    if user_id not in user_data:
        await interaction.response.send_message(f"{user.name} is not on the list.", ephemeral=True)
        return

    if streak < 0:
        await interaction.response.send_message("❌ Streak cannot be negative.", ephemeral=True)
        return

    user_data[user_id]["streak"] = streak
    save_data()
    await interaction.response.send_message(f"✅ {user.name}'s streak has been set to **{streak}**.")

# ---------- Weekly Checkup ----------
def weekly_check():
    for user_id, data in user_data.items():
        if data["workouts"] >= data["goal"]:
            data["streak"] += 1
        else:
            data["streak"] = 0
        data["workouts"] = 0
    save_data()

# ---------- Notifications ----------
async def send_notification(message: str, user_ids: list[int]):
    if not user_ids:
        return

    channel = discord.utils.get(client.get_all_channels(), name="accountabilibuddies")  # CHANGE if needed
    if not channel:
        print("Channel 'accountabilibuddies' not found.")
        return

    mentions = " ".join(f"<@{uid}>" for uid in user_ids)
    await channel.send(f"{mentions}\n{message}")

async def monday_to_wednesday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if data["workouts"] == 0
    ]
    if users_to_tag:
        await send_notification("🏃 You haven't logged any workouts this week! Time to get moving 💪", users_to_tag)

async def thursday_to_friday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if (data["goal"] - data["workouts"]) >= 2
    ]
    if users_to_tag:
        await send_notification("⚠️ You're 2 or more workouts behind your goal this week. Time to catch up!", users_to_tag)

async def saturday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if (data["goal"] - data["workouts"]) >= 1
    ]
    if users_to_tag:
        await send_notification("🕒 It's Saturday! You're still behind your goal. Finish strong 💥", users_to_tag)

async def weekly_check():
    ...
    await send_notification("✅ Weekly reset done! Great work everyone!", list(map(int, user_data.keys())))

# ---------- Scheduler ----------
scheduler = AsyncIOScheduler()
scheduler.add_job(weekly_check, CronTrigger(day_of_week='sun', hour=0, minute=0))

scheduler.add_job(lambda: asyncio.create_task(weekly_check()), CronTrigger(day_of_week='sun', hour=0, minute=0))


# Notifications: 7 AM
for day in ['mon', 'tue', 'wed']:
    scheduler.add_job(
        lambda day=day: asyncio.create_task(monday_to_wednesday_check()),
        CronTrigger(day_of_week=day, hour=7, minute=0)
    )


for day in ['thu', 'fri']:
    scheduler.add_job(
        lambda day=day: asyncio.create_task(monday_to_wednesday_check()),
        CronTrigger(day_of_week=day, hour=7, minute=0)
    )


scheduler.add_job(lambda: asyncio.create_task(saturday_check()), CronTrigger(day_of_week='sat', hour=7, minute=0))

# ---------- Run Bot ----------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
client.run(TOKEN)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)



