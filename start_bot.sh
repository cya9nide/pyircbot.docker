#!/bin/bash

# PyIRCBot Startup Script
# This script starts the IRC bot with proper error handling

echo "Starting PyIRCBot IRC Bot..."
echo "Configuration will be loaded from environment variables"
echo "Make sure you have set up your .env file"
echo ""

# Check if Python 3 is available
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
else
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.6 or higher"
    exit 1
fi

echo "Using Python: $($PYTHON_CMD --version)"

# Check if the bot script exists
if [ ! -f "pyircbot.py" ]; then
    echo "Error: pyircbot.py not found in current directory"
    echo "Please run this script from the bot directory"
    exit 1
fi

# Make the bot script executable
chmod +x pyircbot.py

# Start the bot
echo "Launching PyIRCBot..."
echo "Press Ctrl+C to stop the bot"
echo ""

$PYTHON_CMD pyircbot.py

echo ""
echo "PyIRCBot has stopped." 