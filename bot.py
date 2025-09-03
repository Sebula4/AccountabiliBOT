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
async def workout(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id not in user_data:
        await interaction.response.send_message("You're not on the list. Use `/add_user` to join.", ephemeral=True)
        return

    user_data[user_id]["workouts"] += 1
    save_data()
    await interaction.response.send_message(f"Great job! Workouts this week: {user_data[user_id]['workouts']}")

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

    sorted_users = sorted(user_data.values(), key=lambda x: x["name"].lower())

    lines = [
        f"**{u['name']}**: {u['workouts']} / {u['goal']} / {u['streak']}"
        for u in sorted_users
    ]

    message = "**🏋️ Accountability Stats:**\n" + "\n".join(lines)
    await interaction.response.send_message(message)

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

    channel = discord.utils.get(client.get_all_channels(), name="general")  # CHANGE if needed
    if not channel:
        print("Channel 'general' not found.")
        return

    mentions = " ".join(f"<@{uid}>" for uid in user_ids)
    await channel.send(f"{mentions}\n{message}")

async def monday_to_wednesday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if data["workouts"] == 0
    ]
    if users_to_tag:
        await send_notification("🏃 You haven't logged any workouts this week! Time to get moving 💪", users_to_tag)

async def thursday_to_saturday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if (data["goal"] - data["workouts"]) >= 2
    ]
    if users_to_tag:
        await send_notification("⚠️ You're 2 or more workouts behind your goal this week. Time to catch up!", users_to_tag)

async def sunday_check():
    users_to_tag = [
        int(uid) for uid, data in user_data.items() if (data["goal"] - data["workouts"]) >= 1
    ]
    if users_to_tag:
        await send_notification("🕒 It's Sunday! You're still behind your goal. Finish strong 💥", users_to_tag)

# ---------- Scheduler ----------
scheduler = AsyncIOScheduler()
scheduler.add_job(weekly_check, CronTrigger(day_of_week='sun', hour=0, minute=0))

# Notifications: 7 AM
for day in ['mon', 'tue', 'wed']:
    scheduler.add_job(lambda: asyncio.create_task(monday_to_wednesday_check()), CronTrigger(day_of_week=day, hour=7, minute=0))

for day in ['thu', 'fri', 'sat']:
    scheduler.add_job(lambda: asyncio.create_task(thursday_to_saturday_check()), CronTrigger(day_of_week=day, hour=7, minute=0))

scheduler.add_job(lambda: asyncio.create_task(sunday_check()), CronTrigger(day_of_week='sun', hour=7, minute=0))

# ---------- Run Bot ----------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
client.run(TOKEN)

