# Telegram Advertisement Automation Bot

## Overview
This bot allows you to automate Telegram advertisement posting across multiple groups and channels. It runs through Termux and handles automated login, message forwarding, and group management.

## Features
- One-time login with session persistence
- Automatic joining of target groups/channels
- Message forwarding to multiple groups/channels
- Support for both custom messages and forwarding existing messages
- Interactive menu with Telegram bot interface
- Bulk addition of new marketplace groups

## Installation

### Prerequisites
- Termux app installed on Android
- Python 3.6+ installed in Termux

### Setup
1. Install required packages in Termux:
```bash
pkg update && pkg upgrade
pkg install python git
```

2. Clone this repository:
```bash
git clone https://github.com/yourusername/telegram-ad-bot
cd telegram-ad-bot
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage
1. Run the main script:
```bash
python3 main.py
```

2. First-time setup:
   - Enter your phone number in international format
   - Enter the verification code sent to your Telegram
   - Provide your Telegram bot token (create one via @BotFather)
   - Enter your personal Telegram chat ID

3. Use the interactive menu to:
   - Forward messages
   - Add new marketplace groups
   - Check account status
   - View joined groups

## Configuration
- All settings are stored in `assets/config.toml`
- Target groups/channels are stored in `assets/groups.txt`

## Caution
Use this tool responsibly. Excessive or inappropriate use may lead to account restrictions or bans by Telegram.

## License
This project is for educational purposes only.