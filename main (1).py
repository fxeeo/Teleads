
import os
import asyncio
import json
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import toml

CONFIG_PATH = 'assets/config.toml'
GROUPS_PATH = 'assets/groups.txt'

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    return toml.load(CONFIG_PATH)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        toml.dump(config, f)

async def init_config():
    config = load_config()
    if 'telegram' not in config:
        config['telegram'] = {}
    if 'bot' not in config:
        config['bot'] = {}

    if not config['telegram'].get('session'):
        print("Login to Telegram")
        phone = input("Enter your phone number in international format: ")
        client = TelegramClient(StringSession(), api_id=123456, api_hash='your_api_hash')  # Replace with your credentials
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            try:
                await client.sign_in(phone, input('Enter the code: '))
            except SessionPasswordNeededError:
                await client.sign_in(password=input('Password: '))
        config['telegram']['session'] = client.session.save()
        await client.disconnect()
        save_config(config)

    if not config['bot'].get('token'):
        config['bot']['token'] = input("Enter your bot token: ")
    if not config['bot'].get('chat_id'):
        config['bot']['chat_id'] = input("Enter your admin chat ID: ")
    save_config(config)
    return config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Forward Message", callback_data='forward')],
        [InlineKeyboardButton("Add Marketplace", callback_data='add_marketplace')],
        [InlineKeyboardButton("Add New Account", callback_data='add_account')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an action:", reply_markup=reply_markup)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Selected option: {query.data}")

async def main():
    config = await init_config()
    app = ApplicationBuilder().token(config["bot"]["token"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
