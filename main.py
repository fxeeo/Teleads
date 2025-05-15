#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import logging
import random
import time
from typing import List, Dict, Optional, Union, Tuple

# Import dependencies
try:
    import toml
    from telethon import TelegramClient, events, Button
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.messages import ImportChatInviteRequest
    from telethon.errors import (
        PhoneNumberInvalidError, 
        FloodWaitError,
        ChatAdminRequiredError,
        ChannelPrivateError,
        ChatWriteForbiddenError,
        UserBannedInChannelError,
        InviteHashInvalidError,
        UserAlreadyParticipantError
    )
except ImportError:
    print("Installing required packages...")
    os.system("pip install telethon toml cryptography")
    print("Packages installed. Restarting script...")
    os.execv(sys.executable, ['python3'] + sys.argv)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("assets/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
API_ID = 800812  # Static Telegram API ID (default Telethon app)
API_HASH = "db55ad67a98df35667ca788b97f771f5"  # Static Telegram API Hash
CONFIG_PATH = "assets/config.toml"
GROUPS_PATH = "assets/groups.txt"
SESSION_DIR = "assets/sessions"

class TelegramBot:
    def __init__(self):
        """Initialize the Telegram bot with configuration."""
        self.config = {}
        self.accounts = []
        self.bot_client = None
        self.active_accounts = []
        self.groups = []
        
        # Create necessary directories and files
        self._initialize_directories()
        self._load_config()
        self._load_groups()
        
    def _initialize_directories(self):
        """Create necessary directories and files if they don't exist."""
        os.makedirs("assets", exist_ok=True)
        os.makedirs(SESSION_DIR, exist_ok=True)
        
        # Initialize groups.txt if it doesn't exist
        if not os.path.exists(GROUPS_PATH):
            with open(GROUPS_PATH, "w") as f:
                f.write("# Add group/channel links here, one per line\n")
                
    def _load_config(self):
        """Load configuration from config.toml or create it if it doesn't exist."""
        if not os.path.exists(CONFIG_PATH):
            # First run, create default config
            self.config = {
                "admin_chat_id": None,
                "bot_token": None,
                "accounts": []
            }
            self._save_config()
        else:
            try:
                self.config = toml.load(CONFIG_PATH)
                # Ensure all required keys exist
                if "accounts" not in self.config:
                    self.config["accounts"] = []
                if "admin_chat_id" not in self.config:
                    self.config["admin_chat_id"] = None
                if "bot_token" not in self.config:
                    self.config["bot_token"] = None
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                self.config = {
                    "admin_chat_id": None,
                    "bot_token": None,
                    "accounts": []
                }
    
    def _save_config(self):
        """Save configuration to config.toml."""
        try:
            with open(CONFIG_PATH, "w") as f:
                toml.dump(self.config, f)
            logger.info("Configuration saved successfully.")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def _load_groups(self):
        """Load groups/channels from groups.txt."""
        if os.path.exists(GROUPS_PATH):
            with open(GROUPS_PATH, "r") as f:
                lines = f.readlines()
                self.groups = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        else:
            self.groups = []
    
    def _save_groups(self):
        """Save groups/channels to groups.txt."""
        with open(GROUPS_PATH, "w") as f:
            f.write("# Add group/channel links here, one per line\n")
            for group in self.groups:
                f.write(f"{group}\n")
    
    def add_groups(self, new_groups: List[str]):
        """Add new groups to groups.txt and remove duplicates."""
        # Add new groups to the list
        combined = set(self.groups + new_groups)
        self.groups = list(combined)
        self._save_groups()
    
    async def setup_first_run(self):
        """Setup the bot for the first run, asking for required information."""
        print("\n======= TELEGRAM ADVERTISEMENT BOT SETUP =======")
        
        # Check if bot token is already set
        if not self.config["bot_token"]:
            bot_token = input("\nEnter your Telegram bot token: ")
            self.config["bot_token"] = bot_token
            self._save_config()
        
        # Check if admin chat ID is already set
        if not self.config["admin_chat_id"]:
            admin_chat_id = input("\nEnter your admin chat ID (your Telegram ID): ")
            try:
                admin_chat_id = int(admin_chat_id)
                self.config["admin_chat_id"] = admin_chat_id
                self._save_config()
            except ValueError:
                logger.error("Admin chat ID must be a number.")
                sys.exit(1)
        
        # Add the first account if no accounts exist
        if not self.config["accounts"]:
            print("\nYou need to add at least one Telegram account to use for forwarding messages.")
            phone = input("Enter your phone number in international format (e.g., +12345678900): ")
            
            # Add the account to config
            account_id = len(self.config["accounts"]) + 1
            self.config["accounts"].append({
                "id": account_id,
                "phone": phone,
                "is_active": True
            })
            self._save_config()
            
            # Log in with the account
            await self._login_account(phone)
    
    async def _login_account(self, phone: str) -> bool:
        """Login to a Telegram account and save the session."""
        session_file = os.path.join(SESSION_DIR, f"{phone.replace('+', '')}")
        
        client = TelegramClient(session_file, API_ID, API_HASH)
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                print(f"\nLogging in to Telegram with phone number: {phone}")
                await client.send_code_request(phone)
                code = input("Enter the verification code you received: ")
                try:
                    await client.sign_in(phone, code)
                except Exception as e:
                    if "2FA" in str(e) or "PASSWORD" in str(e).upper():
                        password = input("Enter your 2FA password: ")
                        await client.sign_in(password=password)
            
            # Test if login was successful
            me = await client.get_me()
            logger.info(f"Successfully logged in as {me.first_name} (@{me.username})")
            
            # Join all groups with this account
            await self._join_all_groups(client)
            
            await client.disconnect()
            return True
            
        except PhoneNumberInvalidError:
            logger.error(f"Invalid phone number: {phone}")
            return False
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False
    
    async def _join_all_groups(self, client):
        """Join all groups with a specific client."""
        logger.info(f"Attempting to join {len(self.groups)} groups...")
        
        for group in self.groups:
            try:
                if group.startswith("https://t.me/+") or group.startswith("t.me/+"):
                    # Private group with invite link
                    invite_hash = group.split("+")[1]
                    await client(ImportChatInviteRequest(invite_hash))
                    logger.info(f"Joined private group with hash {invite_hash}")
                else:
                    # Public channel or group
                    if group.startswith("https://t.me/") or group.startswith("t.me/"):
                        channel_username = group.split("/")[-1]
                    else:
                        channel_username = group
                    
                    await client(JoinChannelRequest(channel_username))
                    logger.info(f"Joined public channel/group @{channel_username}")
                
                # Sleep to avoid flood wait
                await asyncio.sleep(2)
                
            except UserAlreadyParticipantError:
                # Already in the group, which is fine
                pass
            except (ChannelPrivateError, InviteHashInvalidError, ChatAdminRequiredError):
                logger.warning(f"Could not join group: {group} - Private, invalid, or requires admin")
            except FloodWaitError as e:
                wait_time = e.seconds
                logger.warning(f"Flood wait for {wait_time} seconds when joining groups")
                if wait_time > 300:  # If wait time is more than 5 minutes
                    logger.info(f"Waiting for {wait_time} seconds due to Telegram limits")
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(wait_time)
            except Exception as e:
                logger.warning(f"Error joining group {group}: {e}")
        
        logger.info("Finished joining groups")
    
    async def start_bot(self):
        """Start the Telegram bot."""
        # Check if we need to set up first
        if not self.config["admin_chat_id"] or not self.config["bot_token"]:
            await self.setup_first_run()
        
        # Start the bot
        self.bot_client = TelegramClient('assets/bot_session', API_ID, API_HASH)
        await self.bot_client.start(bot_token=self.config["bot_token"])
        
        # Register bot command handlers
        self._register_handlers()
        
        logger.info("Telegram bot started successfully!")
        
        # Start and test all client accounts
        await self._initialize_accounts()
        
        # Run the bot until disconnected
        await self.bot_client.run_until_disconnected()
    
    async def _initialize_accounts(self):
        """Initialize all client accounts."""
        self.active_accounts = []
        
        for account in self.config["accounts"]:
            if account.get("is_active", True):
                phone = account["phone"]
                session_file = os.path.join(SESSION_DIR, f"{phone.replace('+', '')}")
                
                # Check if session file exists
                if not os.path.exists(f"{session_file}.session"):
                    logger.info(f"Session file not found for {phone}, logging in...")
                    success = await self._login_account(phone)
                    if not success:
                        continue
                
                # Create client instance for later use
                client = TelegramClient(session_file, API_ID, API_HASH)
                try:
                    await client.connect()
                    if await client.is_user_authorized():
                        me = await client.get_me()
                        logger.info(f"Account {phone} (@{me.username}) is ready")
                        self.active_accounts.append({
                            "client": client,
                            "phone": phone,
                            "username": me.username,
                            "id": account["id"]
                        })
                    else:
                        logger.warning(f"Account {phone} is not authorized, re-login required")
                        await client.disconnect()
                        # Remove the session file
                        if os.path.exists(f"{session_file}.session"):
                            os.remove(f"{session_file}.session")
                        # Try to login again
                        success = await self._login_account(phone)
                        if success:
                            client = TelegramClient(session_file, API_ID, API_HASH)
                            await client.connect()
                            if await client.is_user_authorized():
                                me = await client.get_me()
                                self.active_accounts.append({
                                    "client": client,
                                    "phone": phone,
                                    "username": me.username,
                                    "id": account["id"]
                                })
                except Exception as e:
                    logger.error(f"Error initializing account {phone}: {e}")
        
        logger.info(f"Initialized {len(self.active_accounts)} active accounts out of {len(self.config['accounts'])}")
    
    def _register_handlers(self):
        """Register bot command handlers."""
        @self.bot_client.on(events.NewMessage(pattern='/start'))
        async def start_command(event):
            if event.chat_id != self.config["admin_chat_id"]:
                await event.respond("You are not authorized to use this bot.")
                return
            
            await event.respond(
                "🤖 **Welcome to the Telegram Advertisement Bot**\n\n"
                "Use the buttons below to manage your advertisements and accounts.",
                buttons=[
                    [
                        Button.text("✉️ Forward Message", resize=True),
                        Button.text("➕ Add Marketplace", resize=True)
                    ],
                    [
                        Button.text("👤 Add New Account", resize=True),
                        Button.text("📊 Status", resize=True)
                    ]
                ]
            )
        
        @self.bot_client.on(events.NewMessage(pattern='✉️ Forward Message'))
        async def forward_message_command(event):
            if event.chat_id != self.config["admin_chat_id"]:
                return
            
            await event.respond(
                "Please send me the message you want to forward, or a link to a Telegram message."
            )
            self.bot_client.conversation_state = "waiting_forward_content"
        
        @self.bot_client.on(events.NewMessage(pattern='➕ Add Marketplace'))
        async def add_marketplace_command(event):
            if event.chat_id != self.config["admin_chat_id"]:
                return
            
            await event.respond(
                "Please send me the group/channel links you want to add, one per line.\n"
                "Format: https://t.me/group_name or t.me/+inviteCode"
            )
            self.bot_client.conversation_state = "waiting_marketplace_links"
        
        @self.bot_client.on(events.NewMessage(pattern='👤 Add New Account'))
        async def add_account_command(event):
            if event.chat_id != self.config["admin_chat_id"]:
                return
            
            await event.respond(
                "Please send me the phone number you want to add in international format.\n"
                "Example: +12345678900"
            )
            self.bot_client.conversation_state = "waiting_phone_number"
        
        @self.bot_client.on(events.NewMessage(pattern='📊 Status'))
        async def status_command(event):
            if event.chat_id != self.config["admin_chat_id"]:
                return
            
            status_text = "**📊 Bot Status**\n\n"
            status_text += f"**Active Accounts:** {len(self.active_accounts)}/{len(self.config['accounts'])}\n"
            status_text += f"**Groups/Channels:** {len(self.groups)}\n\n"
            
            # List accounts
            if self.active_accounts:
                status_text += "**Accounts:**\n"
                for i, account in enumerate(self.active_accounts, 1):
                    status_text += f"{i}. {account['phone']} - @{account['username']}\n"
            
            await event.respond(status_text)
        
        # Handle regular messages (conversation flow)
        @self.bot_client.on(events.NewMessage())
        async def handle_messages(event):
            if event.chat_id != self.config["admin_chat_id"]:
                return
            
            # Skip button commands which are handled separately
            if hasattr(event.message, 'text') and event.message.text in [
                "✉️ Forward Message", "➕ Add Marketplace", 
                "👤 Add New Account", "📊 Status"
            ]:
                return
            
            # Get conversation state
            state = getattr(self.bot_client, 'conversation_state', None)
            
            if state == "waiting_forward_content":
                await self._handle_forward_content(event)
                
            elif state == "waiting_marketplace_links":
                await self._handle_marketplace_links(event)
                
            elif state == "waiting_phone_number":
                await self._handle_new_phone_number(event)

    async def _handle_forward_content(self, event):
        """Handle the content to be forwarded."""
        self.bot_client.conversation_state = None
        message_text = event.message.text
        
        # Check if we have any active accounts
        if not self.active_accounts:
            await event.respond(
                "⚠️ No active accounts available for forwarding. Please add accounts first."
            )
            return
        
        # Check if we have any groups
        if not self.groups:
            await event.respond(
                "⚠️ No groups available for forwarding. Please add groups first."
            )
            return
        
        await event.respond("⏳ Processing your request...")
        
        # Check if the message is a Telegram link
        if message_text.startswith(("https://t.me/", "t.me/")):
            try:
                # Extract channel, message_id from link
                parts = message_text.split("/")
                if len(parts) >= 5:  # Format: https://t.me/channel_name/message_id
                    channel_name = parts[-2]
                    message_id = int(parts[-1])
                    
                    status_msg = await event.respond("🔄 Fetching message from link...")
                    
                    # Use the first active account to fetch the message
                    source_client = self.active_accounts[0]["client"]
                    source_message = await source_client.get_messages(channel_name, ids=message_id)
                    
                    if not source_message:
                        await status_msg.edit("⚠️ Could not find the message. Check if the link is valid and the account has access to it.")
                        return
                    
                    # Forward the fetched message
                    await self._forward_to_groups(source_message, status_msg)
                else:
                    await event.respond("⚠️ Invalid message link format. It should be like: https://t.me/channel/123")
            except Exception as e:
                logger.error(f"Error processing message link: {e}")
                await event.respond(f"⚠️ Error processing message link: {str(e)[:100]}...")
        else:
            # Direct message content
            status_msg = await event.respond("🔄 Processing your message...")
            await self._forward_to_groups(event.message, status_msg)
    
    async def _forward_to_groups(self, source_message, status_msg):
        """Forward a message to all groups using account rotation."""
        if not self.active_accounts:
            await status_msg.edit("⚠️ No active accounts available.")
            return
        
        if not self.groups:
            await status_msg.edit("⚠️ No groups configured.")
            return
        
        total_groups = len(self.groups)
        total_accounts = len(self.active_accounts)
        
        # Prepare progress tracking
        success_count = 0
        error_count = 0
        current_group = 0
        
        # Update status message initially
        await status_msg.edit(f"🔄 Forwarding message to {total_groups} groups using {total_accounts} accounts...\n\n0% completed")
        
        # Rotate through accounts for each group
        for i, group in enumerate(self.groups):
            # Select account in rotation
            account_index = i % total_accounts
            account = self.active_accounts[account_index]
            client = account["client"]
            
            try:
                # Format group identifier
                if group.startswith(("https://t.me/", "t.me/")):
                    if "+/" in group or "+?" in group:  # Private group
                        # Extract invite hash
                        if "+/" in group:
                            invite_hash = group.split("+/")[1].split("/")[0]
                        else:
                            invite_hash = group.split("+")[1]
                        
                        # Try to resolve the actual chat entity first
                        try:
                            chat = await client(ImportChatInviteRequest(invite_hash))
                            chat_entity = chat.chats[0]
                        except (UserAlreadyParticipantError, Exception):
                            # If already a participant, get the chat entity a different way
                            # We'll just attempt to send to all dialogs that match
                            async for dialog in client.iter_dialogs():
                                if dialog.entity.id == int(invite_hash):
                                    chat_entity = dialog.entity
                                    break
                            else:
                                # Couldn't find the chat, skip
                                error_count += 1
                                continue
                    else:  # Public channel/group
                        channel_username = group.split("/")[-1]
                        try:
                            chat_entity = await client.get_entity(channel_username)
                        except Exception as e:
                            logger.error(f"Error getting entity for {channel_username}: {e}")
                            error_count += 1
                            continue
                else:
                    # Direct username or ID
                    try:
                        chat_entity = await client.get_entity(group)
                    except Exception as e:
                        logger.error(f"Error getting entity for {group}: {e}")
                        error_count += 1
                        continue
                
                # Forward or send the message
                if hasattr(source_message, 'forward_to'):
                    # This is a telethon Message object
                    await client.forward_messages(chat_entity, source_message)
                else:
                    # This is message content
                    await client.send_message(chat_entity, source_message.text)
                
                success_count += 1
                
                # Update progress every 5 groups or at the end
                current_group = i + 1
                progress = (current_group / total_groups) * 100
                
                if current_group % 5 == 0 or current_group == total_groups:
                    await status_msg.edit(
                        f"🔄 Forwarding message...\n\n"
                        f"Progress: {progress:.1f}% ({current_group}/{total_groups})\n"
                        f"✅ Successful: {success_count} | ❌ Failed: {error_count}"
                    )
                
                # Sleep to avoid hitting rate limits (randomize to appear more natural)
                await asyncio.sleep(random.uniform(1.5, 3.5))
                
            except FloodWaitError as e:
                # Handle flood wait by sleeping and trying the next account
                logger.warning(f"FloodWaitError with account {account['phone']}: {e}")
                error_count += 1
                
                # If the wait time is too long, mark this account as temporarily unavailable
                if e.seconds > 300:  # More than 5 minutes
                    logger.info(f"Account {account['phone']} is rate limited for {e.seconds} seconds")
                    # Move to the next one
                
            except (ChannelPrivateError, ChatAdminRequiredError, UserBannedInChannelError, ChatWriteForbiddenError) as e:
                logger.warning(f"Permission error for group {group}: {e}")
                error_count += 1
                
            except Exception as e:
                logger.error(f"Error forwarding to {group} using account {account['phone']}: {e}")
                error_count += 1
        
        # Final status update
        await status_msg.edit(
            f"✅ Message forwarding complete!\n\n"
            f"Total groups: {total_groups}\n"
            f"✅ Successful: {success_count}\n"
            f"❌ Failed: {error_count}"
        )
    
    async def _handle_marketplace_links(self, event):
        """Handle received group/channel links."""
        self.bot_client.conversation_state = None
        links_text = event.message.text
        
        # Extract links from the text
        links = [line.strip() for line in links_text.split("\n") if line.strip()]
        
        if not links:
            await event.respond("⚠️ No valid links found in your message.")
            return
        
        # Add the links to the groups list
        old_count = len(self.groups)
        self.add_groups(links)
        new_count = len(self.groups)
        added_count = new_count - old_count
        
        # Join the groups with all active accounts
        await event.respond(f"🔄 Added {added_count} new groups/channels. Joining them with {len(self.active_accounts)} accounts...")
        
        join_tasks = []
        for account in self.active_accounts:
            join_tasks.append(self._join_all_groups(account["client"]))
        
        if join_tasks:
            # Run join tasks concurrently
            await asyncio.gather(*join_tasks)
        
        await event.respond(f"✅ Successfully added {added_count} new groups/channels and attempted to join with all accounts.")
    
    async def _handle_new_phone_number(self, event):
        """Handle new phone number addition."""
        self.bot_client.conversation_state = None
        phone = event.message.text.strip()
        
        # Check if phone number is valid
        if not phone.startswith("+") or not phone[1:].isdigit():
            await event.respond("⚠️ Invalid phone number format. Please use international format with '+' prefix.")
            return
        
        # Check if phone number already exists
        for account in self.config["accounts"]:
            if account["phone"] == phone:
                await event.respond(f"⚠️ This phone number ({phone}) is already added to your accounts.")
                return
        
        # Add the account to config
        account_id = max([a.get("id", 0) for a in self.config["accounts"]], default=0) + 1
        self.config["accounts"].append({
            "id": account_id,
            "phone": phone,
            "is_active": True
        })
        self._save_config()
        
        # Try to login with the account
        await event.respond(f"🔄 Attempting to log in with phone number: {phone}")
        success = await self._login_account(phone)
        
        if success:
            await event.respond(f"✅ Successfully added and logged in with phone number: {phone}")
            # Reinitialize accounts to include the new one
            await self._initialize_accounts()
        else:
            await event.respond(f"⚠️ Failed to log in with phone number: {phone}. Please check the number and try again.")
            # Remove the account from config
            self.config["accounts"] = [a for a in self.config["accounts"] if a["phone"] != phone]
            self._save_config()

async def main():
    """Main entry point of the script."""
    # Create the necessary directories
    os.makedirs("assets", exist_ok=True)
    
    # Initialize the bot
    bot = TelegramBot()
    
    # Start the bot
    await bot.start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        print(f"\nCritical error: {e}")
        sys.exit(1)
