#!/usr/bin/env python3
"""
PyIRCBot - IRC Bot
A simple Python-based IRC bot with basic functionality
"""

import socket
import threading
import time
import re
import random
import logging
import urllib.parse
import urllib.request


import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import config
import calendar

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

class PyIRCBot:
    def __init__(self, server=None, port=None, channel=None, 
                 nickname=None, username=None, realname=None):
        # Load environment variables
        load_dotenv()
        
        # Use provided values or fall back to config values
        self.server = server or config.IRC_SERVER
        self.port = port or config.IRC_PORT
        self.channel = channel or config.IRC_CHANNEL
        self.nickname = nickname or config.BOT_NICKNAME
        self.desired_nickname = self.nickname  # Track the nick we actually want
        self.username = username or config.BOT_USERNAME
        self.realname = realname or config.BOT_REALNAME
        self.socket = None
        self.running = False
        
        # Load API keys
        self.weather_api_key = os.getenv('WEATHER_API_KEY')

        # LM Studio settings (OpenAI-compatible local endpoint)
        self.lmstudio_base_url = os.getenv('LMSTUDIO_BASE_URL', 'http://host.docker.internal:1234/v1').rstrip('/')
        self.lmstudio_model = os.getenv('LMSTUDIO_MODEL', '')
        self.lmstudio_api_key = os.getenv('LMSTUDIO_API_KEY', '')
        self.lmstudio_timeout = int(os.getenv('LMSTUDIO_TIMEOUT_SECONDS', '30'))
        self.qa_max_per_window = int(os.getenv('QA_RATE_LIMIT_COUNT', '3'))
        self.qa_window_minutes = int(os.getenv('QA_RATE_LIMIT_WINDOW_MINUTES', '30'))

        # IRC payload safety margin. IRC max line is 512 bytes including command/meta,
        # so keep message chunks conservative to avoid server-side truncation.
        self.irc_message_chunk_size = int(os.getenv('IRC_MESSAGE_CHUNK_SIZE', '380'))

        # Per-user .qa rate tracking: {nickname: [datetime, ...]}
        self.qa_query_history = {}

        # Services auth
        self.auth_command = config.AUTH_COMMAND
        self.auth_delay = config.AUTH_DELAY
        
        # Get current month for tracking
        self.current_month = datetime.now().strftime('%m-%Y')
        
        # Configure logging with monthly rotation
        self.setup_logging()
        
        # Bot commands and responses (using . prefix to avoid Chanserv conflicts)
        self.commands = {
            '.help': self.cmd_help,
            '.time': self.cmd_time,
            '.ping': self.cmd_ping,
            '.dice': self.cmd_dice,
            '.8ball': self.cmd_8ball,
            '.weather': self.cmd_weather,
            '.joke': self.cmd_joke,
            '.stats': self.cmd_stats,
            '.topusers': self.cmd_topusers,
            '.qa': self.cmd_qa,
            '.google': self.cmd_google
        }
        
        # Bot statistics with monthly tracking
        self.stats = {
            'messages_received': 0,
            'commands_processed': 0,
            'start_time': datetime.now(),
            'user_messages': {},  # Track messages per user for loudmouth
            'monthly_stats': {
                self.current_month: {
                    'messages_received': 0,
                    'commands_processed': 0,
                    'user_messages': {}
                }
            }
        }
        
        # Reconstruct stats from existing logs
        self.reconstruct_stats_from_logs()

    def setup_logging(self):
        """Setup logging with monthly rotation"""
        # Get log directory from environment variable or use current directory
        log_dir = os.getenv('LOG_DIR', '.')
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        log_filename = os.path.join(log_dir, f'pyircbot_{self.current_month}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def reconstruct_stats_from_logs(self):
        """Reconstruct statistics from existing log files"""
        log_dir = os.getenv('LOG_DIR', '.')
        
        # Get current month log file
        current_log_file = os.path.join(log_dir, f'pyircbot_{self.current_month}.log')
        
        if os.path.exists(current_log_file):
            try:
                with open(current_log_file, 'r') as f:
                    for line in f:
                        # Parse log lines to reconstruct stats
                        if ' - INFO - <' in line and '> ' in line:
                            # Extract user and message
                            parts = line.split(' - INFO - <')
                            if len(parts) == 2:
                                user_message_part = parts[1]
                                if '> ' in user_message_part:
                                    user_end = user_message_part.find('> ')
                                    user = user_message_part[:user_end]
                                    message = user_message_part[user_end + 2:].strip()
                                    
                                    # Count messages
                                    self.stats['messages_received'] += 1
                                    
                                    # Track user messages
                                    if user not in self.stats['user_messages']:
                                        self.stats['user_messages'][user] = 0
                                    self.stats['user_messages'][user] += 1
                                    
                                    # Track monthly stats
                                    if self.current_month not in self.stats['monthly_stats']:
                                        self.stats['monthly_stats'][self.current_month] = {
                                            'messages_received': 0,
                                            'commands_processed': 0,
                                            'user_messages': {}
                                        }
                                    
                                    self.stats['monthly_stats'][self.current_month]['messages_received'] += 1
                                    
                                    if user not in self.stats['monthly_stats'][self.current_month]['user_messages']:
                                        self.stats['monthly_stats'][self.current_month]['user_messages'][user] = 0
                                    self.stats['monthly_stats'][self.current_month]['user_messages'][user] += 1
                                    
                                    # Count commands
                                    if message.startswith('.'):
                                        self.stats['commands_processed'] += 1
                                        self.stats['monthly_stats'][self.current_month]['commands_processed'] += 1
                
                self.logger.info(f"Reconstructed stats from log: {self.stats['messages_received']} messages, {self.stats['commands_processed']} commands")
            except Exception as e:
                self.logger.error(f"Error reconstructing stats from logs: {e}")

    def check_month_change(self):
        """Check if month has changed and roll logs if necessary"""
        current_month = datetime.now().strftime('%m-%Y')
        if current_month != self.current_month:
            self.logger.info(f"Month changed from {self.current_month} to {current_month}. Rolling logs and stats.")
            
            # Get log directory from environment variable or use current directory
            log_dir = os.getenv('LOG_DIR', '.')
            
            # Archive old log file
            old_log_filename = os.path.join(log_dir, f'pyircbot_{self.current_month}.log')
            if os.path.exists(old_log_filename):
                archive_filename = os.path.join(log_dir, f'pyircbot_{self.current_month}_archive.log')
                os.rename(old_log_filename, archive_filename)
                self.logger.info(f"Archived old log to {archive_filename}")
            
            # Update current month
            self.current_month = current_month
            
            # Setup new logging
            self.setup_logging()
            
            # Initialize new month stats
            if current_month not in self.stats['monthly_stats']:
                self.stats['monthly_stats'][current_month] = {
                    'messages_received': 0,
                    'commands_processed': 0,
                    'user_messages': {}
                }

    def get_monthly_stats(self):
        """Get current month's statistics"""
        return self.stats['monthly_stats'].get(self.current_month, {
            'messages_received': 0,
            'commands_processed': 0,
            'user_messages': {}
        })

    def connect(self):
        """Establish connection to IRC server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server, self.port))
            self.logger.info(f"Connected to {self.server}:{self.port}")
            
            # Send registration commands
            self.send_raw(f"NICK {self.nickname}")
            self.send_raw(f"USER {self.username} 0 * :{self.realname}")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False

    def send_raw(self, message):
        """Send raw message to IRC server"""
        try:
            self.socket.send(f"{message}\r\n".encode('utf-8'))
            self.logger.debug(f"Sent: {message}")
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")

    def send_message(self, target, message):
        """Send message to channel or user"""
        for chunk in self._split_irc_message(message):
            self.send_raw(f"PRIVMSG {target} :{chunk}")

    def _split_irc_message(self, message):
        """Split outgoing text into IRC-safe chunks."""
        if not message:
            return [""]

        text = " ".join(str(message).split())
        max_len = max(64, self.irc_message_chunk_size)

        chunks = []
        while len(text) > max_len:
            split_at = text.rfind(' ', 0, max_len + 1)
            if split_at <= 0:
                split_at = max_len
            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()

        if text:
            chunks.append(text)

        return chunks

    def join_channel(self, channel):
        """Join IRC channel"""
        self.send_raw(f"JOIN {channel}")
        self.logger.info(f"Joined channel: {channel}")

    def handle_message(self, line):
        """Handle incoming IRC messages"""
        # Check for month change first
        self.check_month_change()
        
        # Parse IRC message
        if line.startswith(':'):
            parts = line.split(' ', 2)
            if len(parts) >= 3:
                sender = parts[0][1:].split('!')[0]
                command = parts[1]
                message = parts[2][1:] if parts[2].startswith(':') else parts[2]
                
                self.stats['messages_received'] += 1
                
                # Update monthly stats
                monthly_stats = self.get_monthly_stats()
                monthly_stats['messages_received'] += 1
                
                # Handle PING
                if command == 'PING':
                    self.send_raw(f"PONG :{message}")
                    return

                # Handle NICK change — someone freed our desired nick
                if command == 'NICK' and self.nickname != self.desired_nickname:
                    self._try_reclaim_nick()
                    return

                # Handle QUIT — someone using our desired nick left
                if command == 'QUIT' and sender == self.desired_nickname:
                    self._try_reclaim_nick()
                    return

                # Handle successful nick change (server confirms our NICK)
                if command == 'NICK' and sender == self.nickname:
                    new_nick = message.lstrip(':')
                    if new_nick == self.desired_nickname:
                        self.nickname = self.desired_nickname
                        self.logger.info(f"Reclaimed desired nick '{self.desired_nickname}'")
                    return

                # Handle PRIVMSG
                if command == 'PRIVMSG':
                    # The target is the second part after splitting the message
                    target = parts[2].split(' :')[0] if ' :' in parts[2] else parts[2]
                    actual_message = parts[2].split(' :', 1)[1] if ' :' in parts[2] else ''
                    
                    if target == self.channel:
                        self.handle_channel_message(sender, actual_message)
                    else:
                        self.handle_private_message(sender, actual_message)
        else:
            # Handle non-prefixed messages (like PING from server)
            if line.startswith('PING'):
                pong_msg = line.replace('PING', 'PONG')
                self.send_raw(pong_msg)

    def _authenticate_and_join(self):
        """Send auth command (if configured), wait for vhost to apply, then join channel."""
        if self.auth_command:
            raw = self.auth_command.strip()
            # Convert /msg <target> <text>  →  PRIVMSG <target> :<text>
            if raw.lower().startswith('/msg '):
                raw = raw[5:]  # strip '/msg '
                parts = raw.split(' ', 1)
                target = parts[0]
                text = parts[1] if len(parts) > 1 else ''
                raw = f"PRIVMSG {target} :{text}"
            self.send_raw(raw)
            self.logger.info(f"Sent auth command to services. Waiting {self.auth_delay}s before joining.")
            time.sleep(self.auth_delay)
        self.join_channel(self.channel)

    def _try_reclaim_nick(self):
        """Attempt to reclaim the desired nickname if we're using a fallback."""
        if self.nickname != self.desired_nickname:
            self.send_raw(f"NICK {self.desired_nickname}")

    def handle_channel_message(self, sender, message):
        """Handle messages in the channel"""
        self.logger.info(f"<{sender}> {message}")
        
        # Track user messages for loudmouth stats (only channel messages)
        if sender not in self.stats['user_messages']:
            self.stats['user_messages'][sender] = 0
        self.stats['user_messages'][sender] += 1
        
        # Track monthly user messages
        monthly_stats = self.get_monthly_stats()
        if sender not in monthly_stats['user_messages']:
            monthly_stats['user_messages'][sender] = 0
        monthly_stats['user_messages'][sender] += 1
        
        # Check for bot commands
        for cmd, func in self.commands.items():
            if message.startswith(cmd):
                self.logger.info(f"Command detected: {cmd} from {sender}")
                self.stats['commands_processed'] += 1
                monthly_stats['commands_processed'] += 1
                response = func(sender, message)
                if response:
                    self.logger.info(f"Sending response: {response}")
                    self.send_message(self.channel, response)
                break
        
        # Check for links in the message (Link detection temporarily disabled)
        # links = self.extract_links(message)
        # for link in links:
        #     summary = self.get_link_summary(link)
        #     if summary:
        #         # Add sender info to the summary
        #         full_summary = f"{summary} - shared by {sender}"
        #         self.send_message(self.channel, full_summary)

    def handle_private_message(self, sender, message):
        """Handle private messages"""
        self.logger.info(f"PM from {sender}: {message}")
        
        # Check for bot commands in PM
        for cmd, func in self.commands.items():
            if message.startswith(cmd):
                self.stats['commands_processed'] += 1
                monthly_stats = self.get_monthly_stats()
                monthly_stats['commands_processed'] += 1
                response = func(sender, message)
                if response:
                    self.send_message(sender, response)
                break

    # Bot command handlers
    def cmd_help(self, sender, message):
        """Show available commands"""
        help_text = "Available commands: .help, .time, .ping, .dice, .8ball, .weather, .joke, .stats, .topusers, .qa, .google"
        return help_text

    def cmd_time(self, sender, message):
        """Show current time"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"Current time: {current_time}"

    def cmd_ping(self, sender, message):
        """Respond to ping"""
        return f"Pong! Hello {sender}!"

    def cmd_dice(self, sender, message):
        """Roll dice (default 1d6, or specified like .dice 2d20)"""
        try:
            if message == '.dice':
                return f"{sender} rolled: {random.randint(1, 6)}"
            else:
                # Parse dice notation like .dice 2d20
                dice_match = re.search(r'\.dice (\d+)d(\d+)', message)
                if dice_match:
                    num_dice = int(dice_match.group(1))
                    sides = int(dice_match.group(2))
                    if num_dice > 10 or sides > 100:
                        return "Dice too large! Max 10 dice, 100 sides."
                    rolls = [random.randint(1, sides) for _ in range(num_dice)]
                    total = sum(rolls)
                    return f"{sender} rolled {num_dice}d{sides}: {rolls} (Total: {total})"
                else:
                    return "Usage: .dice or .dice XdY (e.g., .dice 2d20)"
        except:
            return "Invalid dice format! Use .dice or .dice XdY"

    def cmd_8ball(self, sender, message):
        """Magic 8-ball responses"""
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.",
            "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
            "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        return f"Magic 8-Ball says: {random.choice(responses)}"

    def cmd_weather(self, sender, message):
        """Weather command using WeatherAPI.com with forecast support"""
        try:
            # Extract location and forecast type from command
            parts = message.replace('.weather', '').strip().split()
            if not parts:
                return "Usage: .weather <city> or .weather <city> forecast <hours/days> (e.g., .weather London forecast 5 hours). Supports city, state/country: .weather Hollywood FL, .weather Manchester UK"
            
            # Parse location with state/country support
            location_parts = []
            forecast_type = None
            forecast_period = None
            
            # Find where forecast parameters start
            forecast_start = -1
            for i, part in enumerate(parts):
                if part.lower() == 'forecast':
                    forecast_start = i
                    break
            
            if forecast_start != -1:
                # Location is everything before 'forecast'
                location_parts = parts[:forecast_start]
                # Parse forecast parameters
                if len(parts) > forecast_start + 1:
                    try:
                        forecast_period = int(parts[forecast_start + 1])
                        if len(parts) > forecast_start + 2:
                            forecast_type = parts[forecast_start + 2].lower()
                        else:
                            forecast_type = 'hours'  # Default to hours
                    except ValueError:
                        return f"Sorry {sender}, invalid forecast period. Use a number (e.g., .weather London forecast 5 hours)"
            else:
                # No forecast, location is all parts
                location_parts = parts
            
            # Build location string with proper formatting
            location = self._format_location_query(location_parts)
            
            if not self.weather_api_key:
                return f"Sorry {sender}, weather API key not configured."
            
            # Determine API endpoint based on forecast type
            if forecast_type == 'days':
                url = "http://api.weatherapi.com/v1/forecast.json"
                params = {
                    'key': self.weather_api_key,
                    'q': location,
                    'days': min(forecast_period, 7),  # Max 7 days
                    'aqi': 'no'
                }
            elif forecast_type == 'hours':
                url = "http://api.weatherapi.com/v1/forecast.json"
                params = {
                    'key': self.weather_api_key,
                    'q': location,
                    'hours': min(forecast_period, 24),  # Max 24 hours
                    'aqi': 'no'
                }
            else:
                # Current weather
                url = "http://api.weatherapi.com/v1/current.json"
                params = {
                    'key': self.weather_api_key,
                    'q': location,
                    'aqi': 'no'
                }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if forecast_type == 'days':
                return self._format_daily_forecast(data, location, forecast_period)
            elif forecast_type == 'hours':
                return self._format_hourly_forecast(data, location, forecast_period)
            else:
                return self._format_current_weather(data)
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Weather API error: {e}")
            return f"Sorry {sender}, couldn't get weather for that location."
        except KeyError as e:
            self.logger.error(f"Weather data parsing error: {e}")
            return f"Sorry {sender}, weather data format error."
        except Exception as e:
            self.logger.error(f"Weather command error: {e}")
            return f"Sorry {sender}, weather command failed."

    def _format_location_query(self, location_parts):
        """Format location parts into a proper query string for the weather API"""
        if not location_parts:
            return ""
        
        # Handle various formats:
        # "Hollywood, FL" -> "Hollywood, FL"
        # "Hollywood FL" -> "Hollywood, FL" 
        # "Manchester, UK" -> "Manchester, UK"
        # "Manchester, CT" -> "Manchester, CT"
        # "New York, NY" -> "New York, NY"
        
        location_str = " ".join(location_parts)
        
        # If there's a comma, it's already properly formatted
        if ',' in location_str:
            return location_str
        
        # Check if the last part looks like a state abbreviation (2 letters)
        if len(location_parts) >= 2:
            last_part = location_parts[-1].upper()
            # Common state abbreviations
            state_abbrevs = {
                'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
                'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
                'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
                'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
                'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
            }
            
            if last_part in state_abbrevs:
                # Format as "City, State"
                city = " ".join(location_parts[:-1])
                return f"{city}, {last_part}"
        
        # Check if the last part looks like a country code (2-3 letters)
        if len(location_parts) >= 2:
            last_part = location_parts[-1].upper()
            # Common country codes
            country_codes = {
                'US', 'UK', 'CA', 'AU', 'DE', 'FR', 'IT', 'ES', 'JP', 'CN',
                'IN', 'BR', 'MX', 'RU', 'KR', 'NL', 'SE', 'NO', 'DK', 'FI',
                'CH', 'AT', 'BE', 'IE', 'NZ', 'ZA', 'SG', 'MY', 'TH', 'VN'
            }
            
            if last_part in country_codes:
                # Format as "City, Country"
                city = " ".join(location_parts[:-1])
                return f"{city}, {last_part}"
        
        # If no special formatting needed, return as is
        return location_str

    def _shorten_country_name(self, country_name):
        """Shorten country names for cleaner display"""
        country_mapping = {
            'United States of America': 'USA',
            'United Kingdom': 'UK',
            'United States': 'USA',
            'Great Britain': 'UK',
            'England': 'UK',
            'Scotland': 'UK',
            'Wales': 'UK',
            'Northern Ireland': 'UK',
            'Canada': 'CA',
            'Australia': 'AU',
            'Germany': 'DE',
            'France': 'FR',
            'Italy': 'IT',
            'Spain': 'ES',
            'Japan': 'JP',
            'China': 'CN',
            'India': 'IN',
            'Brazil': 'BR',
            'Mexico': 'MX',
            'Russia': 'RU',
            'South Korea': 'KR',
            'Netherlands': 'NL',
            'Sweden': 'SE',
            'Norway': 'NO',
            'Denmark': 'DK',
            'Finland': 'FI',
            'Switzerland': 'CH',
            'Austria': 'AT',
            'Belgium': 'BE',
            'Ireland': 'IE',
            'New Zealand': 'NZ',
            'South Africa': 'ZA',
            'Singapore': 'SG',
            'Malaysia': 'MY',
            'Thailand': 'TH',
            'Vietnam': 'VN'
        }
        
        return country_mapping.get(country_name, country_name)

    def _format_location_display(self, city, region, country):
        """Format location display with state/region information"""
        if region and region != city:
            # If we have a region/state and it's different from the city, include it
            return f"{city}, {region}, {country}"
        else:
            # Just city and country
            return f"{city}, {country}"

    def _format_current_weather(self, data):
        """Format current weather data"""
        location_name = data['location']['name']
        country = self._shorten_country_name(data['location']['country'])
        region = data['location'].get('region', '')  # State/province if available
        temp_c = data['current']['temp_c']
        temp_f = data['current']['temp_f']
        condition = data['current']['condition']['text']
        humidity = data['current']['humidity']
        wind_kph = data['current']['wind_kph']
        wind_mph = data['current']['wind_mph']
        
        # Format location with state if available
        location_display = self._format_location_display(location_name, region, country)
        
        return f"🌤️ {location_display}: {temp_f}°F ({temp_c}°C), {condition}, Humidity: {humidity}%, Wind: {wind_mph} mph ({wind_kph} km/h)"

    def _format_hourly_forecast(self, data, location, hours):
        """Format hourly forecast data"""
        location_name = data['location']['name']
        country = self._shorten_country_name(data['location']['country'])
        region = data['location'].get('region', '')  # State/province if available
        
        forecast_parts = []
        for i, hour_data in enumerate(data['forecast']['forecastday'][0]['hour'][:hours]):
            time = hour_data['time'].split(' ')[1][:5]  # Extract HH:MM
            temp_f = hour_data['temp_f']
            temp_c = hour_data['temp_c']
            condition = hour_data['condition']['text']
            
            forecast_parts.append(f"{time}: {temp_f}°F ({temp_c}°C), {condition}")
        
        # Format location with state if available
        location_display = self._format_location_display(location_name, region, country)
        return f"🌤️ {location_display} - {hours}h forecast: {' | '.join(forecast_parts)}"

    def _format_daily_forecast(self, data, location, days):
        """Format daily forecast data"""
        location_name = data['location']['name']
        country = self._shorten_country_name(data['location']['country'])
        region = data['location'].get('region', '')  # State/province if available
        
        forecast_parts = []
        for i, day_data in enumerate(data['forecast']['forecastday'][:days]):
            date = day_data['date']
            max_f = day_data['day']['maxtemp_f']
            min_f = day_data['day']['mintemp_f']
            max_c = day_data['day']['maxtemp_c']
            min_c = day_data['day']['mintemp_c']
            condition = day_data['day']['condition']['text']
            
            # Format date as MM/DD
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            date_str = date_obj.strftime('%m/%d')
            
            forecast_parts.append(f"{date_str}: {max_f}°F/{min_f}°F ({max_c}°C/{min_c}°C), {condition}")
        
        # Format location with state if available
        location_display = self._format_location_display(location_name, region, country)
        return f"🌤️ {location_display} - {days}d forecast: {' | '.join(forecast_parts)}"

    def cmd_joke(self, sender, message):
        """Tell a random joke"""
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? He was outstanding in his field!",
            "What do you call a fake noodle? An impasta!",
            "Why did the math book look so sad? Because it had too many problems!",
            "What do you call a bear with no teeth? A gummy bear!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a dinosaur that crashes his car? Tyrannosaurus wrecks!",
            "Why did the cookie go to the doctor? Because it was feeling crumbly!"
        ]
        return f"{random.choice(jokes)}"

    def cmd_stats(self, sender, message):
        """Show bot statistics"""
        uptime = datetime.now() - self.stats['start_time']
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        # Get monthly stats
        monthly_stats = self.get_monthly_stats()
        
        # Find the loudmouth (user with most messages) for current month
        monthly_loudmouth = "None"
        monthly_loudmouth_count = 0
        if monthly_stats['user_messages']:
            monthly_loudmouth = max(monthly_stats['user_messages'], key=monthly_stats['user_messages'].get)
            monthly_loudmouth_count = monthly_stats['user_messages'][monthly_loudmouth]
        
        # Find the overall loudmouth (user with most messages)
        overall_loudmouth = "None"
        overall_loudmouth_count = 0
        if self.stats['user_messages']:
            overall_loudmouth = max(self.stats['user_messages'], key=self.stats['user_messages'].get)
            overall_loudmouth_count = self.stats['user_messages'][overall_loudmouth]
        
        return f"{self.nickname} Stats - Uptime: {uptime_str}, Messages: {self.stats['messages_received']}, Commands: {self.stats['commands_processed']} | {self.current_month}: Messages: {monthly_stats['messages_received']}, Commands: {monthly_stats['commands_processed']}, Loudmouth: {monthly_loudmouth} ({monthly_loudmouth_count} messages)"

    def cmd_google(self, sender, message):
        """Search command with DuckDuckGo fallback chain and Google URL fallback."""
        try:
            query = message.replace('.google', '').strip()
            if not query:
                return "Usage: .google <search term>"

            # 1) Primary: ddgs text search (no API key)
            results = self._search_ddgs(query, max_results=3)
            if results:
                return f"🔍 Search results for '{query}': {' | '.join(results)}"

            # 2) Secondary: DuckDuckGo Instant Answer API
            results = self._search_instant_answer(query, max_results=3)
            if results:
                return f"🔍 Search results for '{query}': {' | '.join(results)}"

            # 3) Final fallback: direct search URL
            encoded_query = urllib.parse.quote(query)
            return f"🔍 Search for '{query}': https://www.google.com/search?q={encoded_query}"
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return "Sorry, search failed."

    def _search_ddgs(self, query, max_results=3):
        """Primary search path: ddgs package-backed DuckDuckGo text search."""
        if DDGS is None:
            self.logger.warning("ddgs package not available; skipping ddgs search")
            return []

        try:
            results = []
            with DDGS() as ddgs:
                for idx, item in enumerate(ddgs.text(query, max_results=max_results), start=1):
                    if idx > max_results:
                        break

                    title = (item.get('title') or 'Untitled').strip()
                    snippet = (item.get('body') or item.get('snippet') or '').strip()
                    link = (item.get('href') or item.get('url') or '').strip()

                    if len(title) > 80:
                        title = title[:77] + "..."
                    if len(snippet) > 100:
                        snippet = snippet[:97] + "..."

                    if link and snippet:
                        results.append(f"{len(results)+1}. {title} - {snippet} - {link}")
                    elif link:
                        results.append(f"{len(results)+1}. {title} - {link}")
                    else:
                        results.append(f"{len(results)+1}. {title}")

            return results[:max_results]
        except Exception as e:
            self.logger.error(f"ddgs search error: {e}")
            return []

    def _search_instant_answer(self, query, max_results=3):
        """Secondary search path: DuckDuckGo Instant Answer API."""
        try:
            ddg_url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }

            response = requests.get(ddg_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            results = []

            if data.get('AbstractText'):
                abstract = data['AbstractText'][:100] + "..." if len(data['AbstractText']) > 100 else data['AbstractText']
                results.append(f"1. {abstract} - {data.get('AbstractURL', 'No URL')}")

            for item in data.get('Results', []):
                if len(results) >= max_results:
                    break
                if isinstance(item, dict):
                    text = (item.get('Text') or '').strip()
                    first_url = (item.get('FirstURL') or '').strip()
                    if text:
                        short_text = text[:80] + "..." if len(text) > 80 else text
                        if first_url:
                            results.append(f"{len(results)+1}. {short_text} - {first_url}")
                        else:
                            results.append(f"{len(results)+1}. {short_text}")

            for topic in self._extract_topic_entries(data.get('RelatedTopics', [])):
                if len(results) >= max_results:
                    break
                text = topic.get('Text', '')
                first_url = topic.get('FirstURL', '')
                short_text = text[:80] + "..." if len(text) > 80 else text
                if first_url:
                    results.append(f"{len(results)+1}. {short_text} - {first_url}")
                else:
                    results.append(f"{len(results)+1}. {short_text}")

            return results[:max_results]
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Instant Answer API error: {e}")
            return []

    def _extract_topic_entries(self, related_topics):
        """Flatten both flat and grouped RelatedTopics entries."""
        entries = []
        for topic in related_topics:
            if not isinstance(topic, dict):
                continue
            if topic.get('Text'):
                entries.append(topic)
            for nested in topic.get('Topics', []):
                if isinstance(nested, dict) and nested.get('Text'):
                    entries.append(nested)
        return entries

    def cmd_topusers(self, sender, message):
        """Handle the .topusers command to show top 3 users by message count for current month"""
        monthly_stats = self.get_monthly_stats()
        if monthly_stats['user_messages']:
            top_users = sorted(monthly_stats['user_messages'].items(), key=lambda x: x[1], reverse=True)[:3]
            response = f"Top 3 users for {self.current_month}: "
            for user, count in top_users:
                response += f"{user} ({count} messages), "
            response = response.rstrip(', ')  # Remove trailing comma and space
        else:
            response = f"No user data available for {self.current_month}."
        return response

    def _check_qa_rate_limit(self, sender):
        """Allow only N .qa requests per user in a rolling time window."""
        now = datetime.now()
        window_start = now - timedelta(minutes=self.qa_window_minutes)
        history = self.qa_query_history.get(sender, [])

        # Drop entries outside the rolling window
        history = [ts for ts in history if ts >= window_start]

        if len(history) >= self.qa_max_per_window:
            oldest = min(history)
            retry_after = oldest + timedelta(minutes=self.qa_window_minutes)
            remaining = max(1, int((retry_after - now).total_seconds() // 60) + 1)
            self.qa_query_history[sender] = history
            return False, remaining

        history.append(now)
        self.qa_query_history[sender] = history
        return True, None

    def _ask_lmstudio(self, prompt):
        """Send a prompt to LM Studio's OpenAI-compatible chat completions API."""
        if not self.lmstudio_model:
            return None, "LM Studio model is not configured. Set LMSTUDIO_MODEL in .env."

        # Accept either a base URL (e.g., http://host:1234/v1) or a full
        # completions endpoint (e.g., http://host:1234/v1/chat/completions).
        lower_base = self.lmstudio_base_url.lower()
        if lower_base.endswith('/chat/completions'):
            endpoint = self.lmstudio_base_url
        elif lower_base.endswith('/v1'):
            endpoint = f"{self.lmstudio_base_url}/chat/completions"
        else:
            endpoint = f"{self.lmstudio_base_url}/v1/chat/completions"
        headers = {'Content-Type': 'application/json'}
        if self.lmstudio_api_key:
            headers['Authorization'] = f"Bearer {self.lmstudio_api_key}"

        payload = {
            'model': self.lmstudio_model,
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a concise IRC assistant. Keep responses short and plain text.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.7,
            'max_tokens': int(os.getenv('LMSTUDIO_MAX_TOKENS', '1024'))
        }

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=self.lmstudio_timeout)
            response.raise_for_status()
            data = response.json()

            # Surface explicit API-side error payloads when present.
            if isinstance(data, dict) and 'error' in data:
                err = data.get('error')
                if isinstance(err, dict):
                    err_msg = err.get('message') or err.get('code') or str(err)
                else:
                    err_msg = str(err)
                return None, f"LM Studio error: {err_msg}"

            content = None

            # OpenAI/LM Studio chat-completions style.
            choices = data.get('choices') if isinstance(data, dict) else None
            if isinstance(choices, list) and choices:
                first = choices[0] if isinstance(choices[0], dict) else {}
                message = first.get('message') if isinstance(first, dict) else None
                if isinstance(message, dict):
                    msg_content = message.get('content')
                    if isinstance(msg_content, str):
                        content = msg_content.strip()
                    elif isinstance(msg_content, list):
                        parts = []
                        for item in msg_content:
                            if isinstance(item, dict) and isinstance(item.get('text'), str):
                                parts.append(item['text'])
                        content = " ".join(parts).strip() if parts else None

                    # Qwen3 / reasoning models put the answer in reasoning_content
                    # when content is empty. Extract the last paragraph as the conclusion.
                    if not content and isinstance(message, dict):
                        rc = message.get('reasoning_content') or message.get('thinking')
                        if isinstance(rc, str) and rc.strip():
                            paragraphs = [p.strip() for p in rc.split('\n\n') if p.strip()]
                            content = paragraphs[-1] if paragraphs else rc.strip()

                # Some compatible APIs return text directly in choice.
                if not content and isinstance(first.get('text'), str):
                    content = first['text'].strip()

            # Fallback for nonstandard but simple payloads.
            if not content and isinstance(data, dict) and isinstance(data.get('response'), str):
                content = data['response'].strip()

            if not content:
                self.logger.error(f"LM Studio response parse failed: missing text content; full_response={data!r}")
                return None, "LM Studio returned an empty response."

            # Strip hidden reasoning tags emitted by thinking models (DeepSeek-R1, QwQ, etc.)
            # If the entire response is inside <think> tags (model produced no final answer),
            # extract the last meaningful paragraph from the thinking block as a fallback.
            think_match = re.search(r'<think>([\s\S]*?)</think>', content, flags=re.IGNORECASE)
            stripped = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
            if not stripped and think_match:
                # Pull last non-empty paragraph from thinking block as best-effort answer
                paragraphs = [p.strip() for p in think_match.group(1).split('\n\n') if p.strip()]
                stripped = paragraphs[-1] if paragraphs else ""
            content = stripped

            if not content:
                self.logger.error(f"LM Studio response was only reasoning content; full_response={data!r}")
                return None, "LM Studio returned an empty response."

            return content, None
        except requests.exceptions.RequestException as e:
            err_msg = None
            if getattr(e, 'response', None) is not None:
                try:
                    err_data = e.response.json()
                    if isinstance(err_data, dict):
                        err = err_data.get('error', err_data)
                        if isinstance(err, dict):
                            err_msg = err.get('message') or err.get('code')
                        elif isinstance(err, str):
                            err_msg = err
                except Exception:
                    err_msg = (e.response.text or '')[:180]

            self.logger.error(f"LM Studio request failed: {e}")
            if err_msg:
                return None, f"LM Studio request failed: {err_msg}"
            return None, "LM Studio request failed. Ensure LM Studio server is running and reachable."
        except (KeyError, IndexError, TypeError) as e:
            self.logger.error(f"LM Studio response parse failed: {e}")
            return None, "LM Studio response format was unexpected."

    def cmd_qa(self, sender, message):
        """Ask a question via LM Studio using .qa <question>."""
        question = message.replace('.qa', '', 1).strip()
        if not question:
            return "Usage: .qa <question>"

        allowed, minutes_remaining = self._check_qa_rate_limit(sender)
        if not allowed:
            return f"{sender}: rate limit reached for .qa (max {self.qa_max_per_window} per {self.qa_window_minutes} minutes). Try again in about {minutes_remaining} minute(s)."

        answer, error = self._ask_lmstudio(question)
        if error:
            return f"{sender}: {error}"

        return f"{sender}: {answer}"

    def extract_links(self, message):
        """Extract URLs from message"""
        url_pattern = r'https?://[^\s]+'
        return re.findall(url_pattern, message)

    def is_x_twitter_link(self, url):
        """Check if URL is X/Twitter link"""
        return 'x.com' in url or 'twitter.com' in url

    def is_youtube_link(self, url):
        """Check if URL is YouTube link"""
        return 'youtube.com' in url or 'youtu.be' in url

    def get_link_summary(self, url):
        """Get a detailed summary of a link by scraping the page"""
        try:
            # Set up headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Make the request
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            if self.is_youtube_link(url):
                return self._parse_youtube_video(url, response.text)
            else:
                return self._parse_general_link(url, response.text)
                
        except requests.exceptions.Timeout:
            return f"⏰ Link timeout: {url}"
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error for {url}: {e}")
            return f"❌ Link error: {url}"
        except Exception as e:
            self.logger.error(f"Link summary error for {url}: {e}")
            return f"❌ Link error: {url}"

    def _parse_youtube_video(self, url, html_content):
        """Parse YouTube video for detailed information using oEmbed API"""
        try:
            # Extract video ID from URL
            video_id_match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)', url)
            if not video_id_match:
                return f"📺 YouTube video: {url}"
            
            video_id = video_id_match.group(1)
            
            # Use YouTube's oEmbed API to get video info
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(oembed_url, headers=headers, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            title = data.get('title', 'Unknown Title')
            author = data.get('author_name', 'Unknown Channel')
            
            # Clean up title
            title = re.sub(r'\s+', ' ', title)
            title = title[:80] + "..." if len(title) > 80 else title
            
            return f"📺 YouTube video: {title} - by {author}"
            
        except Exception as e:
            self.logger.error(f"YouTube parsing error: {e}")
            return f"📺 YouTube video: {url}"



    def _parse_general_link(self, url, html_content):
        """Parse general web links"""
        try:
            # Extract title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "No title found"
            
            # Clean up title
            title = re.sub(r'\s+', ' ', title)
            title = title[:80] + "..." if len(title) > 80 else title
            
            return f"🔗 {title}"
            
        except Exception as e:
            self.logger.error(f"General link parsing error: {e}")
            return f"🔗 Link: {url}"

    def run(self):
        """Main bot loop"""
        if not self.connect():
            return
        
        self.running = True
        buffer = ""
        
        try:
            while self.running:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                lines = buffer.split('\r\n')
                buffer = lines.pop()  # Keep incomplete line in buffer
                
                for line in lines:
                    if line.strip():
                        self.handle_message(line)
                        
                        # Handle server responses
                        parts = line.split()
                        numeric = parts[1] if len(parts) > 1 else ''
                        if numeric == "001":  # Welcome message
                            self._authenticate_and_join()
                        elif numeric == "433":  # Nickname in use
                            # Only change if we haven't already fallen back
                            if self.nickname == self.desired_nickname:
                                self.nickname = self.desired_nickname + "_"
                                self.send_raw(f"NICK {self.nickname}")
                                self.logger.warning(f"Nick '{self.desired_nickname}' in use, using '{self.nickname}'")
                        elif "PING" in line and not line.startswith(':'):
                            pong_msg = line.replace("PING", "PONG")
                            self.send_raw(pong_msg)
                            
        except KeyboardInterrupt:
            self.logger.info("Bot interrupted by user")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up bot resources"""
        self.running = False
        if self.socket:
            self.send_raw(f"QUIT :{self.nickname} signing off!")
            self.socket.close()
        self.logger.info("Bot shutdown complete")

def main():
    """Main entry point"""
    print("Starting PyIRCBot...")
    bot = PyIRCBot()  # Will use config values from config.py
    bot.run()

if __name__ == "__main__":
    main() 