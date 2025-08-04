# PyIRCBot Configuration File
# Modify these settings to customize your bot
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# IRC Server Settings
IRC_SERVER = os.getenv('IRC_SERVER', 'your_irc_server_here')
IRC_PORT = int(os.getenv('IRC_PORT', '6667'))
IRC_CHANNEL = os.getenv('IRC_CHANNEL', 'your_channel_here')

# Bot Identity
BOT_NICKNAME = os.getenv('BOT_NICKNAME', 'your_bot_nickname_here')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot_username_here')
BOT_REALNAME = os.getenv('BOT_REALNAME', 'your_bot_realname_here')

# Logging Settings
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = os.getenv('LOG_FILE', 'pyircbot.log')

# Bot Behavior
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')  # Commands start with this character
MAX_DICE_COUNT = int(os.getenv('MAX_DICE_COUNT', '10'))   # Maximum number of dice to roll
MAX_DICE_SIDES = int(os.getenv('MAX_DICE_SIDES', '100'))  # Maximum sides on dice

# Auto-reconnect settings
AUTO_RECONNECT = os.getenv('AUTO_RECONNECT', 'True').lower() == 'true'
RECONNECT_DELAY = int(os.getenv('RECONNECT_DELAY', '30'))  # seconds

# Rate limiting (optional)
RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'False').lower() == 'true'
RATE_LIMIT_SECONDS = int(os.getenv('RATE_LIMIT_SECONDS', '2'))  # Minimum time between commands from same user 