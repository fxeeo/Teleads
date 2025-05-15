import os
import toml
import json
import logging
import asyncio
import re
from pathlib import Path
from telethon import TelegramClient, events
from telethon import functions, types, errors
from telethon.tl.custom import Button
from tabulate import tabulate

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="\x1b[38;5;147m[\x1b[0m%(asctime)s\x1b[38;5;147m]\x1b[0m %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("telethon").setLevel(level=logging.CRITICAL)

# Ensure directories exist
os.makedirs("assets/sessions", exist_ok=True)

# Default config structure
DEFAULT_CONFIG = {
    "telegram": {
        "phone_number": "",
        "api_id": 25916930,
        "api_hash": "2cf8da30d3fed99b1dd8fa58480793ac"
    },
    "bot": {
        "token": "",
        "chat_id": ""
    },
    "sending": {
        "send_interval": 5,
        "loop_interval": 300
    }
}

class TelegramBot:
    def __init__(self):
        self.config_path = "assets/config.toml"
        self.groups_path = "assets/groups.txt"
        
        # Ensure assets directory exists
        os.makedirs("assets", exist_ok=True)
        
        # Create default config file if it doesn't exist
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as f:
                toml.dump(DEFAULT_CONFIG, f)
        
        # Create groups file if it doesn't exist
        if not os.path.exists(self.groups_path):
            with open(self.groups_path, "w", encoding="utf-8") as f:
                f.write("")
        
        # Load config
        with open(self.config_path) as f:
            self.config = toml.loads(f.read())
        
        # Load groups
        with open(self.groups_path, encoding="utf-8") as f:
            self.groups = [i.strip() for i in f if i.strip()]
        
        # Setup client variables
        self.phone_number = self.config["telegram"].get("phone_number", "")
        self.api_id = self.config["telegram"]["api_id"]
        self.api_hash = self.config["telegram"]["api_hash"]
        self.bot_token = self.config["bot"].get("token", "")
        self.chat_id = self.config["bot"].get("chat_id", "")
        
        # Initialize client
        self.client = None
        self.bot = None
        self.user = None
        
        # Message forwarding variables
        self.promotions_chat = None
        self.forward_message = None
        self.custom_message = None
        self.is_running = False
        self.current_state = None

    def save_config(self):
        with open(self.config_path, "w") as f:
            toml.dump(self.config, f)
    
    def save_groups(self):
        with open(self.groups_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.groups))
    
    def tablize(self, headers: list, data: list):
        print(
            tabulate(
                headers=headers,
                tabular_data=data
            ).replace("-", "\x1b[38;5;147m-\x1b[0m")
        )

    async def setup_client(self):
        # First-time setup if not configured
        if not self.phone_number:
            print("\n\x1b[38;5;147m═══ Telegram Account Setup ═══\x1b[0m\n")
            self.phone_number = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Phone number (with country code, e.g. +12025550123): \x1b[0m")
            # Validate phone number format
            while not re.match(r'^\+[0-9]{10,15}$', self.phone_number):
                print("\x1b[31mInvalid phone number format. Please use international format (e.g. +12025550123)\x1b[0m")
                self.phone_number = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Phone number (with country code): \x1b[0m")
            
            self.config["telegram"]["phone_number"] = self.phone_number
            self.save_config()
        
        # Setup Telegram client
        session_path = f"assets/sessions/{self.phone_number}"
        self.client = TelegramClient(
            session=session_path,
            api_id=self.api_id,
            api_hash=self.api_hash
        )
        
        # Connect to Telegram
        await self.client.connect()
        
        # Login if not already authenticated
        if not await self.client.is_user_authorized():
            logging.info(f"Attempting to login \x1b[38;5;147m(\x1b[0m{self.phone_number}\x1b[38;5;147m)\x1b[0m")
            try:
                await self.client.send_code_request(self.phone_number)
                logging.info(f"Sent verification code \x1b[38;5;147m(\x1b[0m{self.phone_number}\x1b[38;5;147m)\x1b[0m")
                
                verification_code = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Verification code: \x1b[0m")
                
                try:
                    await self.client.sign_in(self.phone_number, verification_code)
                except errors.SessionPasswordNeededError:
                    # Handle 2FA if enabled
                    password = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Two-factor authentication password: \x1b[0m")
                    await self.client.sign_in(password=password)
            except Exception as e:
                logging.error(f"Login failed: {str(e)}")
                return False
        
        # Get user info
        self.user = await self.client.get_me()
        logging.info(f"Successfully signed into account \x1b[38;5;147m(\x1b[0m{self.user.username or self.user.phone}\x1b[38;5;147m)\x1b[0m")
        return True

    async def setup_bot(self):
        # Bot setup if not configured
        if not self.bot_token or not self.chat_id:
            print("\n\x1b[38;5;147m═══ Telegram Bot Setup ═══\x1b[0m\n")
            self.bot_token = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Bot token (from @BotFather): \x1b[0m")
            
            while not re.match(r'^\d+:[A-Za-z0-9_-]+$', self.bot_token):
                print("\x1b[31mInvalid bot token format. Please get a valid token from @BotFather\x1b[0m")
                self.bot_token = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Bot token: \x1b[0m")
            
            self.chat_id = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Your chat ID (or username without @): \x1b[0m")
            
            # Save to config
            self.config["bot"]["token"] = self.bot_token
            self.config["bot"]["chat_id"] = self.chat_id
            self.save_config()
        
        # Setup bot client
        self.bot = TelegramClient(
            session="assets/sessions/bot",
            api_id=self.api_id,
            api_hash=self.api_hash
        )
        
        await self.bot.start(bot_token=self.bot_token)
        logging.info("Bot successfully connected!")
        
        # Make sure chat ID starts with @ if it's a username
        if self.chat_id and not self.chat_id.startswith('@') and not self.chat_id.isdigit():
            self.chat_id = '@' + self.chat_id
        
        return True

    async def get_groups(self):
        reply = []

        results = await self.client(functions.messages.GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=types.InputPeerEmpty(),
            limit=200,
            hash=0
        ))

        for dialog in results.chats:
            if isinstance(dialog, types.Channel):
                dialog: types.Channel = dialog
                if dialog.megagroup:
                    reply.append(dialog)

        return reply

    async def get_all_chats(self):
        results = await self.client(functions.messages.GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=types.InputPeerEmpty(),
            limit=200,
            hash=0
        ))        
        return results.chats

    async def join_groups(self):
        joined = 0
        failed = 0
        already_joined = 0
        
        for invite in self.groups:
            if not invite:
                continue
                
            try:
                code = invite
                if "t.me/" in invite:
                    code = invite.split("t.me/")[1]
                elif "https://" in invite:
                    code = invite.split("/")[-1]
                
                # Check if chat is a join link or a simple username
                if "+" in code:
                    try:
                        await self.client(functions.messages.ImportChatInviteRequest(code))
                        logging.info(f"Successfully joined private group \x1b[38;5;147m{invite}\x1b[0m!")
                        joined += 1
                    except errors.UserAlreadyParticipantError:
                        logging.info(f"Already a member of \x1b[38;5;147m{invite}\x1b[0m")
                        already_joined += 1
                    except Exception as e:
                        logging.info(f"Failed to join \x1b[38;5;147m{invite}\x1b[0m: {str(e)}")
                        failed += 1
                else:
                    try:
                        await self.client(functions.channels.JoinChannelRequest(code))
                        logging.info(f"Successfully joined \x1b[38;5;147m{invite}\x1b[0m!")
                        joined += 1
                    except errors.UserAlreadyParticipantError:
                        logging.info(f"Already a member of \x1b[38;5;147m{invite}\x1b[0m")
                        already_joined += 1
                    except Exception as e:
                        logging.info(f"Failed to join \x1b[38;5;147m{invite}\x1b[0m: {str(e)}")
                        failed += 1
                
            except errors.FloodWaitError as e:
                wait_time = int(e.seconds)
                logging.info(f"Rate limited for \x1b[38;5;147m{wait_time}\x1b[0m seconds.")
                
                # Notify user through bot
                if self.bot:
                    await self.bot.send_message(
                        self.chat_id, 
                        f"⚠️ Rate limited for {wait_time} seconds. Waiting before continuing..."
                    )
                
                # Wait the required time
                await asyncio.sleep(wait_time)
                
                # Try again with this invite
                try:
                    if "+" in code:
                        await self.client(functions.messages.ImportChatInviteRequest(code))
                    else:
                        await self.client(functions.channels.JoinChannelRequest(code))
                    logging.info(f"Successfully joined \x1b[38;5;147m{invite}\x1b[0m after waiting!")
                    joined += 1
                except Exception:
                    logging.info(f"Failed to join \x1b[38;5;147m{invite}\x1b[0m even after waiting.")
                    failed += 1
            
            except Exception as e:
                logging.info(f"Failed to join \x1b[38;5;147m{invite}\x1b[0m: {str(e)}")
                failed += 1
            
            # Sleep between joins to avoid rate limits
            await asyncio.sleep(2)
        
        return joined, failed, already_joined

    async def clean_send(self, group, message=None):
        try:
            if message is None:
                # Use the stored forward_message
                await self.client.forward_messages(group, self.forward_message)
            elif isinstance(message, str):
                # Send a custom text message
                await self.client.send_message(group, message)
            else:
                # Forward the specified message object
                await self.client.forward_messages(group, message)
            return True
        except errors.FloodWaitError as e:
            wait_time = int(e.seconds)
            logging.info(f"Rate limited for \x1b[38;5;147m{wait_time}\x1b[0ms.")
            
            # Notify user through bot
            if self.bot:
                await self.bot.send_message(
                    self.chat_id, 
                    f"⚠️ Rate limited for {wait_time} seconds. Waiting before continuing..."
                )
            
            await asyncio.sleep(wait_time)
            return False  # Will retry in the next loop
        except errors.ChatWriteForbiddenError:
            return "FORBIDDEN"
        except Exception as e:
            return str(e)

    async def forward_to_all_groups(self):
        if self.is_running:
            await self.bot.send_message(self.chat_id, "⚠️ A forwarding task is already running!")
            return
        
        self.is_running = True
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        try:
            await self.bot.send_message(
                self.chat_id, 
                "🚀 Starting to forward messages to all groups..."
            )
            
            groups = await self.get_groups()
            total = len(groups)
            
            for i, group in enumerate(groups, 1):
                status_message = f"⏳ Forwarding to group {i}/{total}: {group.title}"
                await self.bot.send_message(self.chat_id, status_message)
                
                # Check if our message is already the latest
                try:
                    last_message = (await self.client.get_messages(group, limit=1))[0]
                    if last_message.from_id and hasattr(last_message.from_id, 'user_id') and last_message.from_id.user_id == self.user.id:
                        logging.info(f"Skipped \x1b[38;5;147m{group.title}\x1b[0m as our message is the latest.")
                        skipped_count += 1
                        continue
                except Exception:
                    # If we can't get the last message, just try to send
                    pass
                
                # Forward the message
                if self.custom_message:
                    result = await self.clean_send(group, self.custom_message)
                else:
                    result = await self.clean_send(group)
                
                if result is True:
                    logging.info(f"Forwarded message to \x1b[38;5;147m{group.title}\x1b[0m!")
                    success_count += 1
                elif result == "FORBIDDEN":
                    logging.info(f"Cannot write to \x1b[38;5;147m{group.title}\x1b[0m!")
                    failed_count += 1
                else:
                    logging.info(f"Failed to forward message to \x1b[38;5;147m{group.title}\x1b[0m: {result}")
                    failed_count += 1
                
                # Sleep between forwards to avoid rate limits
                await asyncio.sleep(self.config["sending"]["send_interval"])
            
            # Final report
            await self.bot.send_message(
                self.chat_id,
                f"✅ Forwarding completed!\n"
                f"- Successfully sent: {success_count}\n"
                f"- Failed: {failed_count}\n"
                f"- Skipped (already sent): {skipped_count}"
            )
        
        except Exception as e:
            await self.bot.send_message(
                self.chat_id,
                f"❌ Error during forwarding: {str(e)}"
            )
        
        finally:
            self.is_running = False

    async def add_marketplace_groups(self, groups_text):
        if not groups_text:
            return 0
        
        new_groups = [g.strip() for g in groups_text.strip().split('\n') if g.strip()]
        added = 0
        
        for group in new_groups:
            if group not in self.groups:
                self.groups.append(group)
                added += 1
        
        # Save updated group list
        self.save_groups()
        return added

    async def setup_bot_handlers(self):
        # Define the menu keyboard
        async def get_main_menu():
            return [
                [Button.text("📤 Forward Message", resize=True)],
                [Button.text("📊 Add Marketplace", resize=True)],
                [Button.text("📋 List Groups", resize=True)],
                [Button.text("🔄 Join All Groups", resize=True)]
            ]
        
        # Start command handler
        @self.bot.on(events.NewMessage(pattern="/start"))
        async def start_handler(event):
            if str(event.chat_id) != str(self.chat_id).replace('@', ''):
                return
            
            await event.respond(
                f"👋 Welcome to your Telegram Advertisement Bot!\n\n"
                f"Connected account: **{self.user.first_name} {self.user.last_name or ''}**\n"
                f"Phone: {self.phone_number}\n"
                f"Groups loaded: {len(self.groups)}\n\n"
                f"Choose an option:",
                buttons=await get_main_menu()
            )
        
        # General message handler
        @self.bot.on(events.NewMessage)
        async def message_handler(event):
            chat_id_str = str(event.chat_id)
            configured_chat_id = str(self.chat_id).replace('@', '')
            
            # Only respond to the configured user
            if chat_id_str != configured_chat_id:
                return
            
            text = event.message.text
            
            # Handle main menu buttons
            if text == "📤 Forward Message":
                self.current_state = "forward_select_method"
                await event.respond(
                    "How would you like to create the message?",
                    buttons=[
                        [Button.text("📝 Write Custom Message", resize=True)],
                        [Button.text("🔗 Use Message Link", resize=True)],
                        [Button.text("🔙 Back to Menu", resize=True)]
                    ]
                )
            
            elif text == "📊 Add Marketplace":
                self.current_state = "add_marketplace"
                await event.respond(
                    "Please send me group/channel links or usernames, one per line.\n\n"
                    "Examples:\n"
                    "- https://t.me/groupname\n"
                    "- @channelname\n"
                    "- channelname\n"
                    "- https://t.me/joinchat/invite_code",
                    buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                )
            
            elif text == "📋 List Groups":
                # Get the first 50 groups from the list
                preview_groups = self.groups[:50]
                total_groups = len(self.groups)
                
                if preview_groups:
                    message = f"📋 Loaded Groups ({total_groups} total):\n\n"
                    for i, group in enumerate(preview_groups, 1):
                        message += f"{i}. {group}\n"
                    
                    if total_groups > 50:
                        message += f"\n... and {total_groups - 50} more groups"
                else:
                    message = "No groups loaded. Add some with 'Add Marketplace' option."
                
                await event.respond(
                    message,
                    buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                )
            
            elif text == "🔄 Join All Groups":
                await event.respond("⏳ Joining all groups, please wait...")
                joined, failed, already = await self.join_groups()
                
                await event.respond(
                    f"✅ Joined {joined} new groups\n"
                    f"⏭️ Already in {already} groups\n"
                    f"❌ Failed to join {failed} groups",
                    buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                )
            
            elif text == "🔙 Back to Menu":
                self.current_state = None
                await event.respond(
                    "Main Menu:",
                    buttons=await get_main_menu()
                )
            
            # Handle write custom message option
            elif text == "📝 Write Custom Message":
                self.current_state = "write_custom_message"
                await event.respond(
                    "Please type your custom message below:",
                    buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                )
            
            # Handle use message link option
            elif text == "🔗 Use Message Link":
                self.current_state = "use_message_link"
                await event.respond(
                    "Please send me a link to the message you want to forward.\n\n"
                    "Example: https://t.me/channel/123",
                    buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                )
            
            # Handle state-based responses
            elif self.current_state == "write_custom_message":
                self.custom_message = text
                self.forward_message = None
                
                await event.respond(
                    f"📝 Custom message set! Preview:\n\n{text}\n\n"
                    f"Ready to forward this message to all groups?",
                    buttons=[
                        [Button.text("✅ Yes, Forward Now", resize=True)],
                        [Button.text("❌ Cancel", resize=True)]
                    ]
                )
                self.current_state = "confirm_forward"
            
            elif self.current_state == "use_message_link":
                # Try to parse the message link
                try:
                    # Format should be like https://t.me/c/1234567890/123 or https://t.me/channelname/123
                    parts = text.strip().split('/')
                    
                    if len(parts) < 4:
                        await event.respond(
                            "⚠️ Invalid message link format. Please try again.",
                            buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                        )
                        return
                    
                    # Distinguish between public and private chats
                    chat_part = parts[-2]
                    msg_id = int(parts[-1])
                    
                    if chat_part.startswith('c'):
                        # Private chat with numeric ID like c/1234567890
                        chat_id = int(chat_part.split('c/')[-1])
                        entity = types.InputPeerChannel(channel_id=chat_id, access_hash=0)
                    else:
                        # Public chat with username
                        entity = chat_part
                    
                    # Try to get the message
                    self.forward_message = await self.client.get_messages(entity, ids=msg_id)
                    
                    if not self.forward_message:
                        await event.respond(
                            "⚠️ Could not find the message. Make sure you have access to it.",
                            buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                        )
                        return
                    
                    self.custom_message = None
                    
                    # Get a preview of the message
                    preview = self.forward_message.text or "[Non-text message]"
                    if len(preview) > 150:
                        preview = preview[:150] + "..."
                    
                    await event.respond(
                        f"🔗 Message found! Preview:\n\n{preview}\n\n"
                        f"Ready to forward this message to all groups?",
                        buttons=[
                            [Button.text("✅ Yes, Forward Now", resize=True)],
                            [Button.text("❌ Cancel", resize=True)]
                        ]
                    )
                    self.current_state = "confirm_forward"
                
                except Exception as e:
                    await event.respond(
                        f"⚠️ Error processing message link: {str(e)}\n\nPlease try again.",
                        buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                    )
            
            elif self.current_state == "confirm_forward":
                if text == "✅ Yes, Forward Now":
                    await event.respond("🚀 Starting to forward messages...")
                    asyncio.create_task(self.forward_to_all_groups())
                    self.current_state = None
                
                elif text == "❌ Cancel":
                    await event.respond(
                        "❌ Forwarding cancelled.",
                        buttons=await get_main_menu()
                    )
                    self.current_state = None
            
            elif self.current_state == "add_marketplace":
                # Process the list of groups/channels
                added = await self.add_marketplace_groups(text)
                
                if added > 0:
                    await event.respond(
                        f"✅ Added {added} new groups/channels!\n\n"
                        f"Would you like to join these groups now?",
                        buttons=[
                            [Button.text("✅ Yes, Join Now", resize=True)],
                            [Button.text("❌ No, Skip", resize=True)]
                        ]
                    )
                    self.current_state = "confirm_join"
                else:
                    await event.respond(
                        "ℹ️ No new groups were added. These might be duplicates.",
                        buttons=[[Button.text("🔙 Back to Menu", resize=True)]]
                    )
            
            elif self.current_state == "confirm_join":
                if text == "✅ Yes, Join Now":
                    await event.respond("⏳ Joining groups, please wait...")
                    joined, failed, already = await self.join_groups()
                    
                    await event.respond(
                        f"✅ Joined {joined} new groups\n"
                        f"⏭️ Already in {already} groups\n"
                        f"❌ Failed to join {failed} groups",
                        buttons=await get_main_menu()
                    )
                    self.current_state = None
                
                elif text == "❌ No, Skip":
                    await event.respond(
                        "👍 Groups added to list but not joined.",
                        buttons=await get_main_menu()
                    )
                    self.current_state = None

    async def start(self):
        # Clear terminal
        os.system("cls" if os.name == "nt" else "clear")
        
        print("\x1b[38;5;147m" + "=" * 50 + "\x1b[0m")
        print("\x1b[38;5;147m   Telegram Advertisement Automation Bot\x1b[0m")
        print("\x1b[38;5;147m" + "=" * 50 + "\x1b[0m")
        
        # Setup Telegram client
        if not await self.setup_client():
            logging.error("Failed to set up Telegram client")
            return
        
        # Join all groups in the list
        if self.groups:
            print("\n\x1b[38;5;147m═══ Group Joining ═══\x1b[0m")
            print(f"Found {len(self.groups)} groups in the list.")
            join_option = input("\x1b[38;5;147m[\x1b[0m?\x1b[38;5;147m]\x1b[0m Join all groups now? (y/n): ").strip().lower()
            
            if join_option == "y" or join_option == "yes":
                print("\nJoining groups, please wait...")
                joined, failed, already = await self.join_groups()
                print(f"\n✅ Joined {joined} new groups")
                print(f"⏭️ Already in {already} groups")
                print(f"❌ Failed to join {failed} groups")
        
        # Setup bot for interactive interface
        if await self.setup_bot():
            await self.setup_bot_handlers()
            
            print("\n\x1b[38;5;147m═══ Bot Setup Complete ═══\x1b[0m")
            print(f"Bot is now running! Start by sending /start to your bot.")
            print(f"Connected account: {self.user.first_name} {self.user.last_name or ''} ({self.phone_number})")
            print(f"Bot token: {self.bot_token[:10]}...{self.bot_token[-5:]}")
            print(f"Chat ID: {self.chat_id}")
            print("\nPress Ctrl+C to stop the bot.")
            
            # Keep the bot running
            await self.bot.run_until_disconnected()
        else:
            logging.error("Failed to set up Telegram bot")

async def main():
    bot = TelegramBot()
    await bot.start()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\x1b[38;5;147m[!]\x1b[