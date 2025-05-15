import os
import toml
import logging
import asyncio
import sys
import re

from telethon import TelegramClient, events
from telethon import functions, types, errors
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="\x1b[38;5;147m[\x1b[0m%(asctime)s\x1b[38;5;147m]\x1b[0m %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("telethon").setLevel(level=logging.CRITICAL)
logging.getLogger("telegram").setLevel(level=logging.CRITICAL)

# Configuration paths
CONFIG_PATH = "assets/config.toml"
GROUPS_PATH = "assets/groups.txt"
SESSION_DIR = "assets/sessions"

# Ensure directories exist
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs("assets", exist_ok=True)

# State definitions for conversation
CHOOSING, FORWARD_TYPE, ENTERING_MESSAGE, ENTERING_LINK, ADDING_MARKETPLACES = range(5)

class TelegramAutomation:
    def __init__(self):
        # Clear terminal and set title
        os.system("cls" if os.name == "nt" else "clear")
        
        # Load or create configuration
        self.config = self.load_config()
        self.phone_number = self.config["telegram"]["phone_number"]
        self.api_id = self.config["telegram"]["api_id"]
        self.api_hash = self.config["telegram"]["api_hash"]
        
        # Load groups
        self.groups = self.load_groups()
        
        # Initialize Telethon client for user account
        self.client = TelegramClient(
            session=f"{SESSION_DIR}/{self.phone_number}",
            api_id=self.api_id,
            api_hash=self.api_hash
        )
        
        # Initialize Telegram bot
        self.bot_token = self.config["telegram"]["bot_token"]
        self.chat_id = self.config["telegram"]["chat_id"]
        
        # Bot application
        self.app = Application.builder().token(self.bot_token).build()
        
        # Setup handlers
        self.setup_bot_handlers()
        
        # Message to forward
        self.forward_message = None
        self.user = None
    
    def load_config(self):
        """Load configuration or create default if not exists"""
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return toml.load(f)
        else:
            # Create default config
            config = {
                "telegram": {
                    "phone_number": "",
                    "api_id": "25281677",  # Default API ID
                    "api_hash": "16a9040b6a16317c77a0168b07c39d38",  # Default API Hash
                    "bot_token": "",
                    "chat_id": ""
                },
                "sending": {
                    "send_interval": 5,  # Seconds between messages
                    "loop_interval": 3600  # Seconds between cycles
                }
            }
            
            # Ask for phone number if not set
            if not config["telegram"]["phone_number"]:
                config["telegram"]["phone_number"] = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Enter your phone number (with country code, e.g., +1234567890)\x1b[38;5;147m:\x1b[0m ")
            
            # Ask for bot token if not set
            if not config["telegram"]["bot_token"]:
                config["telegram"]["bot_token"] = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Enter your Telegram bot token\x1b[38;5;147m:\x1b[0m ")
            
            # Ask for chat ID if not set
            if not config["telegram"]["chat_id"]:
                config["telegram"]["chat_id"] = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Enter your chat ID\x1b[38;5;147m:\x1b[0m ")
            
            # Save config
            with open(CONFIG_PATH, "w") as f:
                toml.dump(config, f)
            
            return config
    
    def save_config(self):
        """Save configuration to file"""
        with open(CONFIG_PATH, "w") as f:
            toml.dump(self.config, f)
    
    def load_groups(self):
        """Load groups from file or create empty file if not exists"""
        if os.path.exists(GROUPS_PATH):
            with open(GROUPS_PATH, "r", encoding="utf-8") as f:
                return [i.strip() for i in f if i.strip()]
        else:
            # Create empty groups file
            with open(GROUPS_PATH, "w", encoding="utf-8") as f:
                pass
            return []
    
    def save_groups(self):
        """Save groups to file"""
        with open(GROUPS_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(self.groups))
    
    def add_groups(self, new_groups):
        """Add new groups to the list and save"""
        # Process and filter new groups
        processed_groups = []
        for group in new_groups:
            group = group.strip()
            if group and group not in self.groups:
                processed_groups.append(group)
        
        # Add new unique groups to the list
        if processed_groups:
            self.groups.extend(processed_groups)
            self.save_groups()
        
        return processed_groups
    
    def setup_bot_handlers(self):
        """Setup Telegram bot handlers"""
        # Command handlers
        self.app.add_handler(CommandHandler("start", self.bot_start))
        
        # Callback query handler for buttons
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Conversation handler for forward message
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.forward_message_callback, pattern='^forward_message$')],
            states={
                FORWARD_TYPE: [CallbackQueryHandler(self.forward_type_callback)],
                ENTERING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_custom_message)],
                ENTERING_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_message_link)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.app.add_handler(conv_handler)
        
        # Conversation handler for adding marketplaces
        add_marketplace_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.add_marketplace_callback, pattern='^add_marketplace$')],
            states={
                ADDING_MARKETPLACES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_new_marketplaces)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.app.add_handler(add_marketplace_handler)
    
    async def bot_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        keyboard = [
            [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
            [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
            [InlineKeyboardButton("📊 Status", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Welcome to Telegram Advertising Automation Bot!", reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "join_groups":
            await query.edit_message_text("Joining groups in progress... This may take a while.")
            result = await self.join_all_groups()
            await query.message.reply_text(result)
            
            # Show main menu again
            keyboard = [
                [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
                [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
                [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
                [InlineKeyboardButton("📊 Status", callback_data="status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Choose an action:", reply_markup=reply_markup)
        
        elif query.data == "status":
            # Get status information
            group_count = len(self.groups)
            active_client = self.client.is_connected()
            
            status_text = f"📊 Bot Status\n\n"
            status_text += f"🔹 Connected Account: {self.phone_number}\n"
            status_text += f"🔹 Client Connected: {'✅' if active_client else '❌'}\n"
            status_text += f"🔹 Total Groups: {group_count}\n"
            status_text += f"🔹 Send Interval: {self.config['sending']['send_interval']}s\n"
            status_text += f"🔹 Cycle Interval: {self.config['sending']['loop_interval']}s\n"
            
            await query.edit_message_text(status_text)
            
            # Show main menu again
            keyboard = [
                [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
                [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
                [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
                [InlineKeyboardButton("📊 Status", callback_data="status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Choose an action:", reply_markup=reply_markup)
    
    async def forward_message_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle forward message button"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [
                InlineKeyboardButton("✏️ Write Custom Message", callback_data="custom_message"),
                InlineKeyboardButton("🔗 Use Message Link", callback_data="message_link")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("How would you like to forward the message?", reply_markup=reply_markup)
        
        return FORWARD_TYPE
    
    async def forward_type_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle forward type selection"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "custom_message":
            await query.edit_message_text("Please enter the custom message you want to forward:")
            return ENTERING_MESSAGE
        elif query.data == "message_link":
            await query.edit_message_text("Please enter the message link (t.me/...) you want to forward:")
            return ENTERING_LINK
    
    async def process_custom_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process custom message entered by the user"""
        custom_message = update.message.text
        
        await update.message.reply_text(f"Starting to forward your custom message to all groups...")
        
        # Forward custom message
        results = await self.forward_custom_message(custom_message)
        await update.message.reply_text(results)
        
        # Show main menu again
        keyboard = [
            [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
            [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
            [InlineKeyboardButton("📊 Status", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
        
        return ConversationHandler.END
    
    async def process_message_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process message link entered by the user"""
        message_link = update.message.text
        
        await update.message.reply_text(f"Processing message link: {message_link}...")
        
        # Forward message from link
        results = await self.forward_from_link(message_link)
        await update.message.reply_text(results)
        
        # Show main menu again
        keyboard = [
            [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
            [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
            [InlineKeyboardButton("📊 Status", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
        
        return ConversationHandler.END
    
    async def add_marketplace_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle add marketplace button"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text("Please enter the group/channel links or usernames to add.\n"
                                     "You can enter multiple links, one per line:")
        
        return ADDING_MARKETPLACES
    
    async def process_new_marketplaces(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process new marketplaces entered by the user"""
        new_groups_text = update.message.text
        new_groups = new_groups_text.strip().split("\n")
        
        # Add new groups
        added_groups = self.add_groups(new_groups)
        
        # Join new groups
        await update.message.reply_text(f"Added {len(added_groups)} new groups. Attempting to join them...")
        
        # Join the newly added groups
        if added_groups:
            join_results = await self.join_specific_groups(added_groups)
            await update.message.reply_text(join_results)
        
        # Show main menu again
        keyboard = [
            [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
            [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
            [InlineKeyboardButton("📊 Status", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel conversation"""
        await update.message.reply_text("Operation cancelled.")
        
        # Show main menu again
        keyboard = [
            [InlineKeyboardButton("📤 Forward Message", callback_data="forward_message")],
            [InlineKeyboardButton("➕ Add Marketplace", callback_data="add_marketplace")],
            [InlineKeyboardButton("👥 Join All Groups", callback_data="join_groups")],
            [InlineKeyboardButton("📊 Status", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
        
        return ConversationHandler.END
    
    async def connect_client(self):
        """Connect to Telegram client and authorize if needed"""
        if not self.client.is_connected():
            await self.client.connect()
        
        if not await self.client.is_user_authorized():
            logging.info(f"Authorization required for {self.phone_number}")
            
            # Request code
            await self.client.send_code_request(self.phone_number)
            logging.info(f"Verification code sent to {self.phone_number}")
            
            # Get code from user
            verification_code = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Enter verification code: ")
            
            # Sign in
            try:
                await self.client.sign_in(self.phone_number, verification_code)
                logging.info("Successfully signed in!")
            except errors.SessionPasswordNeededError:
                # 2FA is enabled
                password = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Two-factor authentication is enabled. Please enter your password: ")
                await self.client.sign_in(password=password)
                logging.info("Successfully signed in with 2FA!")
        
        self.user = await self.client.get_me()
        logging.info(f"Connected as {self.user.first_name} (@{self.user.username})")
    
    async def join_all_groups(self):
        """Join all groups in the list"""
        if not self.client.is_connected():
            await self.connect_client()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        # Check if already in groups
        existing_dialogs = []
        async for dialog in self.client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                if hasattr(dialog.entity, 'username') and dialog.entity.username:
                    existing_dialogs.append(dialog.entity.username.lower())
        
        for group in self.groups:
            # Extract username or invite code
            username = None
            invite_code = None
            
            # Handle different formats
            if "t.me/" in group:
                if "+joinchat/" in group:
                    # Private group invite
                    invite_code = group.split("+joinchat/")[1]
                else:
                    # Public group username
                    username = group.split("t.me/")[1]
            else:
                # Assume it's a username
                username = group
            
            # Skip if already joined
            if username and username.lower() in existing_dialogs:
                skip_count += 1
                continue
            
            try:
                if username:
                    await self.client(JoinChannelRequest(username))
                elif invite_code:
                    await self.client(ImportChatInviteRequest(invite_code))
                
                success_count += 1
                logging.info(f"Successfully joined {group}")
                
                # Wait to avoid flood limits
                await asyncio.sleep(2)
                
            except errors.FloodWaitError as e:
                # Handle rate limiting
                logging.info(f"Rate limited for {e.seconds} seconds. Waiting...")
                await asyncio.sleep(e.seconds)
                fail_count += 1
                
            except Exception as e:
                logging.info(f"Failed to join {group}: {str(e)}")
                fail_count += 1
                
                # Still wait a bit to avoid hitting limits
                await asyncio.sleep(1)
        
        return f"Joined {success_count} groups, failed {fail_count}, skipped {skip_count} (already joined)"
    
    async def join_specific_groups(self, groups_list):
        """Join specific groups from the list"""
        if not self.client.is_connected():
            await self.connect_client()
        
        success_count = 0
        fail_count = 0
        
        for group in groups_list:
            # Extract username or invite code
            username = None
            invite_code = None
            
            # Handle different formats
            if "t.me/" in group:
                if "+joinchat/" in group:
                    # Private group invite
                    invite_code = group.split("+joinchat/")[1]
                else:
                    # Public group username
                    username = group.split("t.me/")[1]
            else:
                # Assume it's a username
                username = group
            
            try:
                if username:
                    await self.client(JoinChannelRequest(username))
                elif invite_code:
                    await self.client(ImportChatInviteRequest(invite_code))
                
                success_count += 1
                logging.info(f"Successfully joined {group}")
                
                # Wait to avoid flood limits
                await asyncio.sleep(2)
                
            except errors.FloodWaitError as e:
                # Handle rate limiting
                logging.info(f"Rate limited for {e.seconds} seconds. Waiting...")
                await asyncio.sleep(e.seconds)
                fail_count += 1
                
            except Exception as e:
                logging.info(f"Failed to join {group}: {str(e)}")
                fail_count += 1
                
                # Still wait a bit to avoid hitting limits
                await asyncio.sleep(1)
        
        return f"Joined {success_count} groups, failed {fail_count}"
    
    async def get_message_from_link(self, message_link):
        """Get message from a Telegram message link"""
        if not self.client.is_connected():
            await self.connect_client()
        
        # Parse message link
        match = re.match(r"https?://t\.me/(?:c/)?([^/]+)/(\d+)", message_link)
        if not match:
            return None
        
        chat_id, message_id = match.groups()
        message_id = int(message_id)
        
        try:
            # If it's a private channel (c/1234567890/123)
            if chat_id.isdigit():
                channel_id = int(chat_id)
                # For private channels, we need to add -100 prefix
                channel_id = -1000000000000 - channel_id
            else:
                # For public channels, use the username
                channel_id = chat_id
            
            # Get the message
            message = await self.client.get_messages(channel_id, ids=message_id)
            return message
            
        except Exception as e:
            logging.error(f"Error getting message from link: {str(e)}")
            return None
    
    async def forward_from_link(self, message_link):
        """Forward message from link to all groups"""
        if not self.client.is_connected():
            await self.connect_client()
        
        # Get message from link
        message = await self.get_message_from_link(message_link)
        if not message:
            return "Failed to get message from link. Please check the link and try again."
        
        # Forward to all groups
        success_count = 0
        fail_count = 0
        
        for group in self.groups:
            try:
                # Extract username or invite code
                if "t.me/" in group:
                    if "+joinchat/" in group:
                        # Skip private groups for now
                        fail_count += 1
                        continue
                    else:
                        # Public group username
                        chat_id = group.split("t.me/")[1]
                else:
                    # Assume it's a username
                    chat_id = group
                
                # Forward message
                await self.client.forward_messages(chat_id, message)
                success_count += 1
                
                # Wait between forwards to avoid flood limits
                await asyncio.sleep(self.config["sending"]["send_interval"])
                
            except errors.FloodWaitError as e:
                # Handle rate limiting
                logging.info(f"Rate limited for {e.seconds} seconds. Waiting...")
                await asyncio.sleep(e.seconds)
                
                # Try again
                try:
                    await self.client.forward_messages(chat_id, message)
                    success_count += 1
                except:
                    fail_count += 1
                
            except Exception as e:
                logging.error(f"Failed to forward to {group}: {str(e)}")
                fail_count += 1
                
                # Still wait a bit to avoid hitting limits
                await asyncio.sleep(1)
        
        return f"Forwarded message to {success_count} groups, failed for {fail_count} groups"
    
    async def forward_custom_message(self, message_text):
        """Forward custom message to all groups"""
        if not self.client.is_connected():
            await self.connect_client()
        
        success_count = 0
        fail_count = 0
        
        for group in self.groups:
            try:
                # Extract username or invite code
                if "t.me/" in group:
                    if "+joinchat/" in group:
                        # Skip private groups for now
                        fail_count += 1
                        continue
                    else:
                        # Public group username
                        chat_id = group.split("t.me/")[1]
                else:
                    # Assume it's a username
                    chat_id = group
                
                # Send message
                await self.client.send_message(chat_id, message_text)
                success_count += 1
                
                # Wait between sends to avoid flood limits
                await asyncio.sleep(self.config["sending"]["send_interval"])
                
            except errors.FloodWaitError as e:
                # Handle rate limiting
                logging.info(f"Rate limited for {e.seconds} seconds. Waiting...")
                await asyncio.sleep(e.seconds)
                
                # Try again
                try:
                    await self.client.send_message(chat_id, message_text)
                    success_count += 1
                except:
                    fail_count += 1
                
            except Exception as e:
                logging.error(f"Failed to send to {group}: {str(e)}")
                fail_count += 1
                
                # Still wait a bit to avoid hitting limits
                await asyncio.sleep(1)
        
        return f"Sent message to {success_count} groups, failed for {fail_count} groups"
    
    async def run(self):
        """Run the automation"""
        # Connect to Telegram client
        await self.connect_client()
        
        # Auto-join groups on startup
        logging.info("Joining groups in the background...")
        asyncio.create_task(self.join_all_groups())
        
        # Start bot
        logging.info(f"Starting Telegram bot with token {self.bot_token[:5]}...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logging.info("Bot is running! Press Ctrl+C to stop.")
        
        # Keep the script running
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            # Graceful shutdown
            await self.app.stop()
            await self.client.disconnect()

async def main():
    automation = TelegramAutomation()
    await automation.run()

if __name__ == "__main__":
    asyncio.run(main())
