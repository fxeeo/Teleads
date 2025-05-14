#!/usr/bin/env python3
import os
import sys
import asyncio
import toml
import logging
import re
import time
from telethon import TelegramClient, events, errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChannelPrivateError, InviteHashInvalidError
from telethon.errors.rpcerrorlist import PhoneNumberInvalidError, PhoneCodeInvalidError
from telethon.sessions import StringSession
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
PHONE, CODE, PASSWORD, TOKEN, CHAT_ID, MENU, FORWARD_TYPE, MSG_LINK, CUSTOM_MSG, ADD_MARKETPLACE = range(10)

# Configuration file paths
CONFIG_FILE = "assets/config.toml"
GROUPS_FILE = "assets/groups.txt"

# Ensure assets directory exists
os.makedirs("assets", exist_ok=True)

# Create empty files if they don't exist
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        f.write("[telegram]\napi_id = 1234567\napi_hash = \"abcdefghijklmnopqrstuvwxyz\"\nsession = \"\"\n\n[bot]\ntoken = \"\"\nchat_id = \"\"\n")

if not os.path.exists(GROUPS_FILE):
    with open(GROUPS_FILE, "w") as f:
        f.write("")

# Load API credentials from environment or use defaults
API_ID = int(os.environ.get("TELEGRAM_API_ID", 25210057))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "8b57739366a70f8ca4d86de099de7ca1")

class TelegramAutomationBot:
    def __init__(self):
        self.config = self._load_config()
        self.client = None
        self.bot = None
        self.chat_id = None
        self.bot_token = None

    def _load_config(self):
        """Load configuration from TOML file"""
        try:
            return toml.load(CONFIG_FILE)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {"telegram": {"session": "", "api_id": API_ID, "api_hash": API_HASH}, 
                   "bot": {"token": "", "chat_id": ""}}

    def _save_config(self):
        """Save configuration to TOML file"""
        try:
            with open(CONFIG_FILE, "w") as f:
                toml.dump(self.config, f)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    async def _load_groups(self):
        """Load groups/channels from file"""
        try:
            with open(GROUPS_FILE, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            logger.error(f"Error loading groups: {e}")
            return []

    async def _save_groups(self, groups):
        """Save groups/channels to file"""
        try:
            with open(GROUPS_FILE, "w") as f:
                f.write("\n".join(groups))
        except Exception as e:
            logger.error(f"Error saving groups: {e}")

    async def _add_groups(self, new_groups):
        """Add new groups/channels to file"""
        existing_groups = await self._load_groups()
        
        # Clean and validate new groups
        cleaned_groups = []
        for group in new_groups:
            group = group.strip()
            if group and group not in existing_groups:
                cleaned_groups.append(group)
                
        # Add unique new groups
        if cleaned_groups:
            all_groups = existing_groups + cleaned_groups
            await self._save_groups(all_groups)
            return len(cleaned_groups)
        return 0

    async def login(self, phone=None, code=None, password=None):
        """Login to Telegram account"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            
        # Use saved session if available
        session = self.config["telegram"].get("session", "")
        
        # Create client with session
        self.client = TelegramClient(
            StringSession(session),
            self.config["telegram"].get("api_id", API_ID),
            self.config["telegram"].get("api_hash", API_HASH),
            device_model="Termux",
            system_version="Android",
            app_version="1.0"
        )
        
        await self.client.connect()
        
        # If already authorized, return success
        if await self.client.is_user_authorized():
            return True, "Already logged in"
        
        # Handle phone number input
        if phone is None:
            return False, "Please enter your phone number"
        
        try:
            # Send code request
            await self.client.send_code_request(phone)
            return False, "Code sent. Please enter verification code"
        except PhoneNumberInvalidError:
            return False, "Invalid phone number. Please try again"
        except FloodWaitError as e:
            return False, f"Too many attempts. Please wait {e.seconds} seconds"
        except Exception as e:
            return False, f"Error sending code: {str(e)}"

    async def verify_code(self, phone, code):
        """Verify the authentication code"""
        try:
            # Sign in with code
            await self.client.sign_in(phone, code)
            
            # Save session
            session_string = StringSession.save(self.client.session)
            self.config["telegram"]["session"] = session_string
            self._save_config()
            
            return True, "Successfully logged in"
        except PhoneCodeInvalidError:
            return False, "Invalid code. Please try again"
        except SessionPasswordNeededError:
            return False, "Two-step verification enabled. Please enter your password"
        except FloodWaitError as e:
            return False, f"Too many attempts. Please wait {e.seconds} seconds"
        except Exception as e:
            return False, f"Error verifying code: {str(e)}"

    async def verify_password(self, password):
        """Verify the two-step verification password"""
        try:
            # Sign in with password
            await self.client.sign_in(password=password)
            
            # Save session
            session_string = StringSession.save(self.client.session)
            self.config["telegram"]["session"] = session_string
            self._save_config()
            
            return True, "Successfully logged in"
        except Exception as e:
            return False, f"Error verifying password: {str(e)}"

    async def join_all_groups(self):
        """Join all groups/channels from the list"""
        groups = await self._load_groups()
        joined = 0
        skipped = 0
        errors = 0
        
        for group in groups:
            try:
                # Handle t.me invite links
                if "t.me/" in group:
                    if "t.me/+" in group or "t.me/joinchat/" in group:
                        # Extract the hash part from invite link
                        invite_hash = group.split("/")[-1]
                        try:
                            await self.client(ImportChatInviteRequest(invite_hash))
                            joined += 1
                            await asyncio.sleep(2)  # Prevent flood
                        except InviteHashInvalidError:
                            skipped += 1
                            logger.warning(f"Invalid invite link: {group}")
                        except Exception as e:
                            errors += 1
                            logger.error(f"Error joining via invite link {group}: {str(e)}")
                    else:
                        # Regular channel/group username
                        username = group.split("/")[-1]
                        try:
                            await self.client(JoinChannelRequest(username))
                            joined += 1
                            await asyncio.sleep(2)  # Prevent flood
                        except Exception as e:
                            errors += 1
                            logger.error(f"Error joining channel {username}: {str(e)}")
                # Handle usernames without links
                elif group.startswith("@"):
                    username = group[1:]  # Remove @ symbol
                    try:
                        await self.client(JoinChannelRequest(username))
                        joined += 1
                        await asyncio.sleep(2)  # Prevent flood
                    except Exception as e:
                        errors += 1
                        logger.error(f"Error joining channel {username}: {str(e)}")
                # Plain channel/group username
                else:
                    try:
                        await self.client(JoinChannelRequest(group))
                        joined += 1
                        await asyncio.sleep(2)  # Prevent flood
                    except Exception as e:
                        errors += 1
                        logger.error(f"Error joining channel {group}: {str(e)}")
            except FloodWaitError as e:
                wait_time = e.seconds
                logger.warning(f"Flood limit hit, waiting for {wait_time} seconds")
                await asyncio.sleep(wait_time)
                # Try again with this group
                try:
                    await self.client(JoinChannelRequest(group))
                    joined += 1
                except Exception:
                    errors += 1
            except Exception as e:
                errors += 1
                logger.error(f"Unexpected error joining {group}: {str(e)}")
                
        return joined, skipped, errors

    async def forward_message(self, message_content, is_link=False):
        """Forward a message to all groups"""
        groups = await self._load_groups()
        sent = 0
        failed = 0
        
        # Get the message from link if it's a link
        if is_link:
            try:
                # Parse message link
                # Format: https://t.me/c/1234567890/123 or https://t.me/username/123
                parts = message_content.split('/')
                
                if len(parts) < 4:
                    return 0, 0, "Invalid message link format"
                
                # Check if it's a private channel (has 'c' in the URL)
                if 'c' in parts:
                    # For private channels: https://t.me/c/1234567890/123
                    # Find the index of 'c'
                    c_index = parts.index('c')
                    if len(parts) <= c_index + 2:
                        return 0, 0, "Invalid message link format"
                    
                    channel_id = int(parts[c_index + 1])
                    message_id = int(parts[c_index + 2])
                    
                    # Need to convert channel_id
                    channel_id = -1000000000000 - channel_id
                    
                    # Get the message
                    message = await self.client.get_messages(channel_id, ids=message_id)
                else:
                    # For public channels: https://t.me/username/123
                    username = parts[3]
                    message_id = int(parts[4])
                    
                    # Get the message
                    message = await self.client.get_messages(username, ids=message_id)
                
                if not message:
                    return 0, 0, "Message not found"
                
                # Now forward to all groups
                for group in groups:
                    try:
                        await self.client.send_message(group, message)
                        sent += 1
                        await asyncio.sleep(3)  # Prevent flood detection
                    except Exception as e:
                        logger.error(f"Error forwarding to {group}: {str(e)}")
                        failed += 1
                        
                return sent, failed, "Message forwarded successfully"
            except Exception as e:
                logger.error(f"Error processing message link: {str(e)}")
                return 0, 0, f"Error processing message link: {str(e)}"
        else:
            # Send custom message to all groups
            for group in groups:
                try:
                    await self.client.send_message(group, message_content)
                    sent += 1
                    await asyncio.sleep(3)  # Prevent flood detection
                except Exception as e:
                    logger.error(f"Error sending to {group}: {str(e)}")
                    failed += 1
            
            return sent, failed, "Message sent successfully"

    async def set_bot_token(self, token):
        """Set the bot token and save to config"""
        try:
            # Test token by getting bot info
            bot = telegram.Bot(token)
            bot_info = await bot.get_me()
            
            # Save token to config
            self.config["bot"]["token"] = token
            self.bot_token = token
            self._save_config()
            
            return True, f"Bot token verified: @{bot_info.username}"
        except Exception as e:
            return False, f"Invalid bot token: {str(e)}"

    async def set_chat_id(self, chat_id):
        """Set the chat ID and save to config"""
        # Validate chat ID
        if not chat_id.lstrip('-').isdigit():
            return False, "Invalid chat ID. Please enter a valid numeric ID"
        
        # Save chat ID to config
        self.config["bot"]["chat_id"] = chat_id
        self.chat_id = chat_id
        self._save_config()
        
        return True, "Chat ID saved successfully"

    def start_bot(self):
        """Start the Telegram bot"""
        self.bot_token = self.config["bot"].get("token", "")
        self.chat_id = self.config["bot"].get("chat_id", "")
        
        # If token and chat ID are set, start bot
        if self.bot_token and self.chat_id:
            # Create application
            application = Application.builder().token(self.bot_token).build()
            
            # Add handlers
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", self.command_start)],
                states={
                    MENU: [
                        CallbackQueryHandler(self.button_forward, pattern="^forward$"),
                        CallbackQueryHandler(self.button_add_marketplace, pattern="^add_marketplace$"),
                        CallbackQueryHandler(self.button_stats, pattern="^stats$"),
                        CallbackQueryHandler(self.button_help, pattern="^help$"),
                    ],
                    FORWARD_TYPE: [
                        CallbackQueryHandler(self.button_msg_link, pattern="^msg_link$"),
                        CallbackQueryHandler(self.button_custom_msg, pattern="^custom_msg$"),
                        CallbackQueryHandler(self.button_back_to_menu, pattern="^back$"),
                    ],
                    MSG_LINK: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_msg_link),
                        CallbackQueryHandler(self.button_back_to_forward, pattern="^back$"),
                    ],
                    CUSTOM_MSG: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_custom_msg),
                        CallbackQueryHandler(self.button_back_to_forward, pattern="^back$"),
                    ],
                    ADD_MARKETPLACE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_add_marketplace),
                        CallbackQueryHandler(self.button_back_to_menu, pattern="^back$"),
                    ],
                },
                fallbacks=[CommandHandler("cancel", self.cancel)],
            )
            
            application.add_handler(conv_handler)
            
            # Start the Bot
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            return True
        else:
            return False

    # Bot command handlers
    async def command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send a message when the command /start is issued."""
        # Check if the user is authorized
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("You are not authorized to use this bot.")
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("Forward Message", callback_data="forward")],
            [InlineKeyboardButton("Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("Stats", callback_data="stats")],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Welcome to Telegram Automation Bot! Select an option:", reply_markup=reply_markup)
        return MENU

    async def button_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the forward button."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("Use Message Link", callback_data="msg_link")],
            [InlineKeyboardButton("Write Custom Message", callback_data="custom_msg")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="How would you like to forward a message?", reply_markup=reply_markup)
        return FORWARD_TYPE
    
    async def button_msg_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle message link option."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [[InlineKeyboardButton("Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Please send the message link (e.g., https://t.me/channel/123):",
            reply_markup=reply_markup
        )
        return MSG_LINK
    
    async def handle_msg_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the message link."""
        message_link = update.message.text
        
        # Check if it looks like a valid message link
        if not re.match(r"https?://t\.me/[a-zA-Z0-9_/]+", message_link):
            await update.message.reply_text("Invalid message link format. Please try again.")
            return MSG_LINK
        
        await update.message.reply_text("Processing message link...")
        
        # Forward the message
        loop = asyncio.get_event_loop()
        sent, failed, msg = await loop.create_task(self.forward_message(message_link, is_link=True))
        
        await update.message.reply_text(f"{msg}\nSent to {sent} groups, failed for {failed} groups.")
        
        # Return to menu
        keyboard = [
            [InlineKeyboardButton("Forward Message", callback_data="forward")],
            [InlineKeyboardButton("Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("Stats", callback_data="stats")],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select an option:", reply_markup=reply_markup)
        return MENU
    
    async def button_custom_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle custom message option."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [[InlineKeyboardButton("Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Please type your custom message to forward to all groups:",
            reply_markup=reply_markup
        )
        return CUSTOM_MSG
    
    async def handle_custom_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the custom message."""
        message_content = update.message.text
        
        await update.message.reply_text("Sending your message to all groups...")
        
        # Forward the message
        loop = asyncio.get_event_loop()
        sent, failed, msg = await loop.create_task(self.forward_message(message_content, is_link=False))
        
        await update.message.reply_text(f"{msg}\nSent to {sent} groups, failed for {failed} groups.")
        
        # Return to menu
        keyboard = [
            [InlineKeyboardButton("Forward Message", callback_data="forward")],
            [InlineKeyboardButton("Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("Stats", callback_data="stats")],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select an option:", reply_markup=reply_markup)
        return MENU
    
    async def button_add_marketplace(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle add marketplace button."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [[InlineKeyboardButton("Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Please send a list of group/channel links or usernames to join (one per line):",
            reply_markup=reply_markup
        )
        return ADD_MARKETPLACE
    
    async def handle_add_marketplace(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process the marketplace list."""
        marketplace_list = update.message.text.split("\n")
        
        await update.message.reply_text("Processing marketplace list...")
        
        # Add groups
        loop = asyncio.get_event_loop()
        added = await loop.create_task(self._add_groups(marketplace_list))
        
        await update.message.reply_text(f"Added {added} new groups/channels to the list.")
        
        # Join groups
        await update.message.reply_text("Joining new groups/channels...")
        joined, skipped, errors = await loop.create_task(self.join_all_groups())
        
        await update.message.reply_text(f"Joined {joined} groups, skipped {skipped}, errors: {errors}")
        
        # Return to menu
        keyboard = [
            [InlineKeyboardButton("Forward Message", callback_data="forward")],
            [InlineKeyboardButton("Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("Stats", callback_data="stats")],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select an option:", reply_markup=reply_markup)
        return MENU
    
    async def button_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle stats button."""
        query = update.callback_query
        await query.answer()
        
        # Get stats
        loop = asyncio.get_event_loop()
        groups = await loop.create_task(self._load_groups())
        
        # Get client info
        me = await self.client.get_me()
        username = f"@{me.username}" if me.username else "No username"
        
        stats_msg = (
            f"🔹 Account: {me.first_name} {me.last_name if me.last_name else ''} ({username})\n"
            f"🔹 Phone: {me.phone if me.phone else 'Not available'}\n"
            f"🔹 Groups/Channels: {len(groups)}\n"
        )
        
        keyboard = [[InlineKeyboardButton("Back to Menu", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=stats_msg, reply_markup=reply_markup)
        return MENU
    
    async def button_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle help button."""
        query = update.callback_query
        await query.answer()
        
        help_msg = (
            "🔹 *Forward Message*: Send a message to all groups/channels\n"
            "🔹 *Add Marketplace*: Add new groups/channels and join them\n"
            "🔹 *Stats*: View account and groups statistics\n\n"
            "To manage your groups/channels list manually, edit the file: assets/groups.txt"
        )
        
        keyboard = [[InlineKeyboardButton("Back to Menu", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=help_msg, reply_markup=reply_markup, parse_mode="Markdown")
        return MENU
    
    async def button_back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Go back to main menu."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("Forward Message", callback_data="forward")],
            [InlineKeyboardButton("Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("Stats", callback_data="stats")],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Select an option:", reply_markup=reply_markup)
        return MENU
    
    async def button_back_to_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Go back to forward options."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("Use Message Link", callback_data="msg_link")],
            [InlineKeyboardButton("Write Custom Message", callback_data="custom_msg")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="How would you like to forward a message?", reply_markup=reply_markup)
        return FORWARD_TYPE
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel and end the conversation."""
        await update.message.reply_text("Operation cancelled. Type /start to begin again.")
        return ConversationHandler.END


async def main():
    print("Starting Telegram Advertisement Automation Bot...")
    
    # Create bot instance
    bot = TelegramAutomationBot()
    
    # Check if already configured
    session = bot.config["telegram"].get("session", "")
    bot_token = bot.config["bot"].get("token", "")
    chat_id = bot.config["bot"].get("chat_id", "")
    
    # Initialize client
    bot.client = TelegramClient(
        StringSession(session),
        bot.config["telegram"].get("api_id", API_ID),
        bot.config["telegram"].get("api_hash", API_HASH),
        device_model="Termux",
        system_version="Android",
        app_version="1.0"
    )
    
    await bot.client.connect()
    
    # Check if needs setup
    if not session or not await bot.client.is_user_authorized():
        print("Login required. Please follow the steps below:")
        
        # Get phone number
        phone = input("Enter your phone number (with country code): ")
        
        # Start login process
        success, message = await bot.login(phone)
        print(message)
        
        if not success:
            # Get verification code
            code = input("Enter the verification code: ")
            
            # Verify code
            success, message = await bot.verify_code(phone, code)
            print(message)
            
            if not success and "password" in message.lower():
                # Get two-step verification password
                password = input("Enter your two-step verification password: ")
                
                # Verify password
                success, message = await bot.verify_password(password)
                print(message)
    
    # Check if logged in successfully
    if not await bot.client.is_user_authorized():
        print("Login failed. Please try again.")
        return
    
    print("Successfully logged in!")
    
    # Join all groups/channels
    print("Joining groups/channels...")
    joined, skipped, errors = await bot.join_all_groups()
    print(f"Joined {joined} groups, skipped {skipped}, errors: {errors}")
    
    # Check if bot token and chat ID are set
    if not bot_token:
        bot_token = input("Enter your bot token: ")
        success, message = await bot.set_bot_token(bot_token)
        print(message)
        
        if not success:
            print("Invalid bot token. Please try again.")
            return
    
    if not chat_id:
        chat_id = input("Enter your chat ID: ")
        success, message = await bot.set_chat_id(chat_id)
        print(message)
        
        if not success:
            print("Invalid chat ID. Please try again.")
            return
    
    # Start the bot
    print("Starting bot...")
    await bot.client.disconnect()
    if bot.start_bot():
        print("Bot started successfully!")
    else:
        print("Failed to start bot. Check your configuration.")


if __name__ == "__main__":
    asyncio.run(main())
