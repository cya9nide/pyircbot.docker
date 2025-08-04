# PyIRCBot - Dockerized IRC Bot

A lightweight, containerized IRC bot built with Python and Docker. Features monthly statistics tracking, weather integration, and persistent log storage.
Tested only with Gamesurge.

## 🚀 Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/cya9nide/pyircbot.docker.git
   cd pyircbot.docker
   ```

2. **Configure your bot**:
   ```bash
   cp env.example .env
   # Edit .env with your IRC server and bot settings
   ```

3. **Start the bot**:
   ```bash
   docker compose up -d
   ```

4. **View logs**:
   ```bash
   docker compose logs -f pyircbot
   ```

## 📋 Features

- **🔄 Monthly Statistics**: Tracks user activity on a monthly basis with automatic log rotation
- **📊 Loudmouth Detection**: Identifies the user with the most messages in the current month
- **👥 Top Users**: Shows the top 3 most active users for the current month
- **🌤️ Weather Integration**: Get current weather information for any location
- **🔍 Search Integration**: Google search functionality using DuckDuckGo API
- **📝 Persistent Logging**: Automatic monthly log archiving with American date format
- **🐳 Docker Containerized**: Lightweight Alpine Linux container with auto-restart
- **💾 Persistent Data**: Logs and data survive container restarts and system reboots

## 📦 Available Commands

| Command | Description |
|---------|-------------|
| `.help` | Shows available commands |
| `.time` | Shows current date and time |
| `.ping` | Responds with "Pong!" |
| `.dice [number]` | Rolls dice (e.g., `.dice 20` for a 20-sided die) |
| `.8ball [question]` | Magic 8-ball responses |
| `.weather [location]` | Current weather info (supports city, state/country) |
| `.joke` | Tells a random joke |
| `.stats` | Shows bot statistics and monthly loudmouth |
| `.topusers` | Lists top 3 users for current month |
| `.google [query]` | Google search with top 3 results |

## 🐳 Docker Management

### Start the bot
```bash
docker compose up -d
```

### Stop the bot
```bash
docker compose down
```

### View logs
```bash
# Follow logs in real-time
docker compose logs -f pyircbot

# View recent logs
docker compose logs pyircbot
```

### Restart the bot
```bash
docker compose restart pyircbot
```

### Update and rebuild
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

## ⚙️ Configuration

### Environment Variables

Copy `env.example` to `.env` and configure your settings:

```bash
# IRC Server Settings
IRC_SERVER=your_irc_server_here
IRC_PORT=6667
IRC_CHANNEL=your_channel_here

# Bot Identity
BOT_NICKNAME=your_bot_nickname_here
BOT_USERNAME=your_bot_username_here
BOT_REALNAME=your_bot_realname_here

# Optional: Weather API Key
# WEATHER_API_KEY=your_weatherapi.com_api_key_here
```

### Configuration Priority

The bot uses values in this priority order:
1. **Runtime parameters** (passed to constructor)
2. **Environment variables** (from `.env` file)
3. **Default values** (in `config.py`)

## 📁 File Structure

```
pyircbot.docker/
├── Dockerfile              # Container definition
├── docker-compose.yml      # Docker Compose configuration
├── .dockerignore          # Files to exclude from build
├── pyircbot.py           # Main bot application
├── config.py             # Configuration module
├── requirements.txt       # Python dependencies
├── env.example           # Environment template
├── .env                  # Your configuration (create this)
├── README.md             # This file
└── data/                 # Persistent log storage (auto-created)
    ├── pyircbot_MM-YYYY.log
    └── pyircbot_MM-YYYY_archive.log
```

## 📊 Logging and Data

### Monthly Log Rotation
- Logs are stored in `./data/` directory
- Monthly logs: `pyircbot_MM-YYYY.log` (e.g., `pyircbot_08-2025.log`)
- Archived logs: `pyircbot_MM-YYYY_archive.log`
- Logs persist between container restarts and system reboots

### Statistics Tracking
- **Monthly loudmouth**: User with most messages in current month
- **Top users**: Top 3 most active users for current month
- **Command usage**: Tracks all bot command usage
- **Uptime tracking**: Bot uptime and message statistics

## 🔧 Troubleshooting

### Check container status
```bash
docker compose ps
```

### View container logs
```bash
docker compose logs pyircbot
```

### Access container shell
```bash
docker compose exec pyircbot sh
```

### Check persistent data
```bash
ls -la data/
```

### Rebuild from scratch
```bash
docker compose down
docker system prune -f
docker compose build --no-cache
docker compose up -d
```

## 🛠️ Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python pyircbot.py
```

### Building the Image
```bash
docker compose build
```

### Testing
```bash
# Test the bot locally
python test_bot.py
```

## 📝 License

This project is open source and available under the [MIT License](LICENSE).

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📞 Support

If you encounter any issues:
1. Check the logs: `docker compose logs pyircbot`
2. Verify your `.env` configuration
3. Ensure Docker is running properly
4. Check the troubleshooting section above

---

**Note**: The `data/` directory contains runtime logs and is excluded from git via `.gitignore`. This directory is created automatically when the container runs and persists between restarts. 
