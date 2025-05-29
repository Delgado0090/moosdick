import os
import random
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# Initialize DB
conn = sqlite3.connect("bigbigger.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    kir INTEGER DEFAULT 0,
    last_use TEXT,
    last_random TEXT,
    win_streak INTEGER DEFAULT 0,
    longest_kir INTEGER DEFAULT 0,
    shortest_kir INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS loans (
    lender_id INTEGER,
    borrower_id INTEGER,
    amount INTEGER
)
''')

conn.commit()

# Utility Functions
def get_player(user_id, username):
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    if not data:
        cursor.execute("INSERT INTO players (user_id, username, kir, longest_kir, shortest_kir) VALUES (?, ?, ?, ?, ?)",
                       (user_id, username, 0, 0, 0))
        conn.commit()
    return cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)).fetchone()

def update_kir(user_id, amount):
    cursor.execute("UPDATE players SET kir = kir + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def set_time(user_id, field):
    now = datetime.now().isoformat()
    cursor.execute(f"UPDATE players SET {field} = ? WHERE user_id = ?", (now, user_id))
    conn.commit()

def can_use(user_id, field, hours):
    cursor.execute(f"SELECT {field} FROM players WHERE user_id = ?", (user_id,))
    last_time = cursor.fetchone()[0]
    if not last_time:
        return True
    return datetime.now() - datetime.fromisoformat(last_time) >= timedelta(hours=hours)

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_player(user.id, user.username)
    await update.message.reply_text(f"Welcome {user.username} to Big Bigger! Use /play to grow your Kir!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = get_player(user.id, user.username)

    if not can_use(user.id, "last_use", 12):
        await update.message.reply_text("You must wait 12 hours before playing again.")
        return

    change = random.randint(-5, 15)
    update_kir(user.id, change)
    set_time(user.id, "last_use")

    new_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (user.id,)).fetchone()[0]

    cursor.execute("SELECT longest_kir, shortest_kir FROM players WHERE user_id = ?", (user.id,))
    longest, shortest = cursor.fetchone()
    if new_kir > longest:
        cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ?", (new_kir, user.id))
    if shortest == 0 or new_kir < shortest:
        cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ?", (new_kir, user.id))
    conn.commit()

    await update.message.reply_text(f"{user.username}, your Kir changed by {change}. Now: {new_kir}")

async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    attacker = get_player(user.id, user.username)

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /fight <user_id>")
        return

    try:
        defender_id = int(context.args[0])
    except:
        await update.message.reply_text("Invalid user ID.")
        return

    if user.id == defender_id:
        await update.message.reply_text("You can't fight yourself.")
        return

    defender = get_player(defender_id, "Unknown")

    attacker_kir = attacker[2]
    defender_kir = defender[2]

    if attacker_kir < 1 or defender_kir < 1:
        await update.message.reply_text("Both players need at least 1 Kir to fight.")
        return

    total = attacker_kir + defender_kir
    attacker_chance = attacker_kir / total

    if random.random() < attacker_chance:
        winner_id = user.id
        loser_id = defender_id
    else:
        winner_id = defender_id
        loser_id = user.id

    fight_points = random.randint(1, min(attacker_kir, defender_kir, 10))
    update_kir(winner_id, fight_points)
    update_kir(loser_id, -fight_points)

    for pid in [attacker[0], defender[0]]:
        if pid == winner_id:
            cursor.execute("UPDATE players SET win_streak = win_streak + 1 WHERE user_id = ?", (pid,))
        else:
            cursor.execute("UPDATE players SET win_streak = 0 WHERE user_id = ?", (pid,))
    conn.commit()

    for pid in [attacker[0], defender[0]]:
        current_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (pid,)).fetchone()[0]
        cursor.execute("SELECT longest_kir, shortest_kir FROM players WHERE user_id = ?", (pid,))
        longest, shortest = cursor.fetchone()
        if current_kir > longest:
            cursor.execute("UPDATE players SET longest_kir = ? WHERE user_id = ?", (current_kir, pid))
        if shortest == 0 or current_kir < shortest:
            cursor.execute("UPDATE players SET shortest_kir = ? WHERE user_id = ?", (current_kir, pid))
    conn.commit()

    winner_kir = cursor.execute("SELECT kir FROM players WHERE user_id = ?", (winner_id,)).fetchone()[0]
    ranks = cursor.execute("SELECT user_id FROM players ORDER BY kir DESC").fetchall()
    rank_map = {uid: i+1 for i, (uid,) in enumerate(ranks)}

    await update.message.reply_text(
        f"\u2694\ufe0f Fight Result:\nWinner: {winner_id} (+{fight_points})\nLoser: {loser_id} (-{fight_points})\n"
        f"{winner_id} Rank: {rank_map[winner_id]}, Kir: {winner_kir}"
    )
