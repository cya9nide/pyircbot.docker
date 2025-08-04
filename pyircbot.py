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
        self.username = username or config.BOT_USERNAME
        self.realname = realname or config.BOT_REALNAME
        self.socket = None
        self.running = False
        
        # Load API keys
        self.weather_api_key = os.getenv('WEATHER_API_KEY')
        
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
            '.google': self.cmd_google,
            '.topusers': self.cmd_topusers
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
        self.send_raw(f"PRIVMSG {target} :{message}")

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
        help_text = "Available commands: .help, .time, .ping, .dice, .8ball, .weather, .joke, .stats, .google"
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
        
        return f"PyIRCBot Stats - Uptime: {uptime_str}, Messages: {self.stats['messages_received']}, Commands: {self.stats['commands_processed']} | {self.current_month}: Messages: {monthly_stats['messages_received']}, Commands: {monthly_stats['commands_processed']}, Loudmouth: {monthly_loudmouth} ({monthly_loudmouth_count} messages)"

    def cmd_google(self, sender, message):
        """Google search command with top 3 results using DuckDuckGo API"""
        try:
            query = message.replace('.google', '').strip()
            if not query:
                return "Usage: .google <search term>"
            
            # Use DuckDuckGo Instant Answer API (no API key required)
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
            
            # Add instant answer if available
            if data.get('AbstractText'):
                abstract = data['AbstractText'][:100] + "..." if len(data['AbstractText']) > 100 else data['AbstractText']
                results.append(f"1. {abstract} - {data.get('AbstractURL', 'No URL')}")
            
            # Add related topics
            for i, topic in enumerate(data.get('RelatedTopics', [])[:3-len(results)]):
                if isinstance(topic, dict) and topic.get('Text'):
                    text = topic['Text'][:80] + "..." if len(topic['Text']) > 80 else topic['Text']
                    results.append(f"{len(results)+1}. {text}")
            
            # If we don't have enough results, add some generic suggestions
            while len(results) < 3:
                results.append(f"{len(results)+1}. Search for '{query}' on Google")
            
            if results:
                return f"🔍 Search results for '{query}': {' | '.join(results)}"
            else:
                # Fallback to Google search URL
                encoded_query = urllib.parse.quote(query)
                return f"🔍 Search for '{query}': https://www.google.com/search?q={encoded_query}"
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Search API error: {e}")
            encoded_query = urllib.parse.quote(query)
            return f"🔍 Search for '{query}': https://www.google.com/search?q={encoded_query}"
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return "Sorry, search failed."

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
                        if "001" in line:  # Welcome message
                            self.join_channel(self.channel)
                        elif "433" in line:  # Nickname in use
                            self.nickname += str(random.randint(1, 999))
                            self.send_raw(f"NICK {self.nickname}")
                        elif "PING" in line:
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
            self.send_raw("QUIT :PyIRCBot signing off!")
            self.socket.close()
        self.logger.info("Bot shutdown complete")

def main():
    """Main entry point"""
    print("Starting PyIRCBot...")
    bot = PyIRCBot()  # Will use config values from config.py
    bot.run()

if __name__ == "__main__":
    main() 