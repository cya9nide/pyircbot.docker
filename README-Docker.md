# PyIRCBot Docker Setup

This directory contains the Docker configuration for running PyIRCBot in a containerized environment.

## Quick Start

1. **Set up your environment file**:
   ```bash
   cp env.example .env
   # Edit .env with your IRC server and bot settings
   ```

2. **Build and run the container**:
   ```bash
   docker-compose up -d
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f pyircbot
   ```

4. **Stop the bot**:
   ```bash
   docker-compose down
   ```

## Configuration

### Environment Variables
The bot uses the `.env` file for configuration. Copy `env.example` to `.env` and edit with your settings:

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

### Persistent Data
- **Logs**: Stored in the `./data` directory and persist between container restarts
- **Monthly logs**: Automatically rotated and archived in the data directory
- **Configuration**: The `.env` file is mounted read-only into the container

## Docker Commands

### Build the image
```bash
docker-compose build
```

### Start the bot
```bash
docker-compose up -d
```

### Stop the bot
```bash
docker-compose down
```

### View logs
```bash
# Follow logs in real-time
docker-compose logs -f pyircbot

# View recent logs
docker-compose logs pyircbot
```

### Restart the bot
```bash
docker-compose restart pyircbot
```

### Update and rebuild
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## File Structure

```
pyircbot.docker/
├── Dockerfile              # Container definition
├── docker-compose.yml      # Docker Compose configuration
├── .dockerignore          # Files to exclude from build
├── pyircbot.py           # Main bot application
├── config.py             # Configuration module
├── start_bot.sh          # Startup script
├── requirements.txt       # Python dependencies
├── env.example           # Environment template
├── .env                  # Your configuration (create this)
└── data/                 # Persistent log storage (gitignored)
    ├── pyircbot_MM-YYYY.log
    └── pyircbot_MM-YYYY_archive.log
```

**Note**: The `data/` directory contains runtime logs and is excluded from git via `.gitignore`. This directory is created automatically when the container runs and persists between restarts.

## Features

- **Lightweight**: Uses Alpine Linux for minimal image size
- **Persistent**: Logs and data survive container restarts
- **Auto-restart**: Container automatically restarts on failure
- **Monthly rotation**: Logs are automatically rotated monthly
- **Environment-based**: Configuration via environment variables

## Troubleshooting

### Check container status
```bash
docker-compose ps
```

### View container logs
```bash
docker-compose logs pyircbot
```

### Access container shell
```bash
docker-compose exec pyircbot sh
```

### Check persistent data
```bash
ls -la data/
```

### Rebuild from scratch
```bash
docker-compose down
docker system prune -f
docker-compose build --no-cache
docker-compose up -d
``` 