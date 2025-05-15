# Telegram Advertisement Bot

A high-speed, Termux-compatible Telegram advertisement bot for bulk forwarding of messages across multiple groups or channels using multiple Telegram accounts.

## Features

- **Multi-Account Support**: Use multiple Telegram accounts in rotation to avoid spam detection
- **Interactive Setup**: First-run setup via terminal prompts
- **Secure Credential Storage**: All credentials stored in encrypted config file
- **Message Forwarding**: Forward original message content to multiple groups
- **Account Rotation**: Smart rotation between accounts to avoid spam detection
- **Automatic Group Joining**: Accounts automatically join groups from your list
- **User-Friendly Bot Interface**: Telegram bot with intuitive button controls
- **Marketplace Management**: Add new groups/channels directly from the bot interface
- **Termux Compatibility**: Fully compatible with Android Termux environment

## Installation

### Prerequisites

- Python 3.8 or higher
- Termux (if using on Android) or any Linux/macOS environment

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/telegram-ad-bot.git
   cd telegram-ad-bot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create required directories:
   ```
   mkdir -p assets .vscode
   ```

4. Run the bot for the first time:
   ```
   python3 main.py
   ```
   
   The first run will guide you through the setup process:
   - Enter your Telegram phone number
   - Enter the Telegram Bot Token (create one via @BotFather)
   - Enter your admin chat ID

5. After setup, the bot will create necessary configuration files and start running.

## Usage

### Bot Commands

Once the bot is running, you can interact with it via Telegram. The bot offers several features through its button menu:

- **Forward Message**: Forward a message to all groups
- **Add Marketplace**: Add new group/channel links
- **Add New Account**: Connect a new Telegram account
- **View Statistics**: See forwarding statistics
- **Settings**: Configure bot behavior

### Adding More Accounts

1. Click on "Add New Account" in the bot menu
2. Follow the instructions to authenticate a new account
3. The new account will be added to the rotation

### Adding Groups/Channels

1. Click on "Add Marketplace" in the bot menu
2. Send a list of group/channel invite links
3. The bot will attempt to join all groups with all available accounts

### Message Forwarding

1. Click on "Forward Message" in the bot menu
2. Either:
   - Type a new message to forward
   - Paste a Telegram message link to forward its content
3. The bot will distribute the message across all groups, rotating between accounts

## File Structure

```
telegram-ad-bot/
├── .vscode/
│   └── settings.json      # VS Code settings
├── assets/
│   ├── config.toml        # Configuration file
│   └── groups.txt         # List of groups/channels
├── main.py                # Main application
├── requirements.txt       # Python dependencies
└── README.md              # Documentation
```

## Security Notes

- Session files are encrypted for security
- Credentials are never hardcoded in the source
- Config file permissions are restricted to the owner

## Troubleshooting

### Common Issues

1. **Bot not responding**:
   - Check if the bot token is valid
   - Ensure you've started a chat with your bot

2. **Account login failures**:
   - Verify the phone number format (include country code)
   - Check if the account has security restrictions

3. **Message forwarding errors**:
   - Some groups may have restrictions on forwarding
   - Check if your accounts have proper permissions in the groups

### Termux-Specific Issues

1. **Storage permission**:
   ```
   termux-setup-storage
   ```

2. **Keep bot running after closing Termux**:
   ```
   nohup python3 main.py &
   ```

## Important Notice

- Use this tool responsibly and ethically
- Respect Telegram's Terms of Service
- Avoid excessive messaging that could be considered spam
- The developer is not responsible for any misuse of this tool

## License

This project is licensed under the MIT License - see the LICENSE file for details.