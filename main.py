
import asyncio
import os
import toml
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

CONFIG_PATH = "assets/config.toml"
GROUPS_PATH = "assets/groups.txt"
SESSIONS_DIR = "assets/sessions"

os.makedirs(SESSIONS_DIR, exist_ok=True)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"accounts": [], "bot": {}}
    return toml.load(CONFIG_PATH)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config, f)

async def add_account():
    phone = input("Enter phone number in international format: ")
    client = TelegramClient(StringSession(), api_id=123456, api_hash="your_api_hash")  # Replace with real API
    await client.connect()
    await client.send_code_request(phone)
    code = input("Enter the code you received: ")
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        pw = input("Two-step verification enabled. Enter your password: ")
        await client.sign_in(password=pw)

    string = client.session.save()
    client.disconnect()

    config = load_config()
    config["accounts"].append({"phone": phone, "session": string})
    save_config(config)

    print(f"Account {phone} added.")

def ensure_config_keys(config):
    if "bot" not in config:
        config["bot"] = {}
    if "accounts" not in config:
        config["accounts"] = []
    save_config(config)

async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send the message you want to forward or paste a Telegram message link.")

async def add_marketplace_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send the group/channel links (one per line).")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "forward":
        await forward_handler(update, context)
    elif query.data == "marketplace":
        await add_marketplace_handler(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Forward Message", callback_data="forward")],
        [InlineKeyboardButton("Add Marketplace", callback_data="marketplace")],
        [InlineKeyboardButton("Add Account", callback_data="add_account")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an option:", reply_markup=reply_markup)

async def main():
    if not os.path.exists(CONFIG_PATH):
        print("No configuration found.")
        bot_token = input("Enter your bot token: ")
        chat_id = input("Enter your Telegram chat ID: ")
        config = {"bot": {"token": bot_token, "chat_id": chat_id}, "accounts": []}
        save_config(config)
        await add_account()
    else:
        config = load_config()
        ensure_config_keys(config)

    app = ApplicationBuilder().token(config["bot"]["token"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), forward_handler))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
