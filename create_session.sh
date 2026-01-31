#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "======================================================================"
echo "  Telegram Session Creator for Docker Deployment"
echo "======================================================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ ERROR: Docker is not installed${NC}"
    echo ""
    echo "Please install Docker first:"
    echo "  - macOS: https://docs.docker.com/desktop/install/mac-install/"
    echo "  - Linux: https://docs.docker.com/engine/install/"
    echo "  - Windows: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ ERROR: .env file not found${NC}"
    echo ""
    echo "Please create .env file with your credentials:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with your Telegram API credentials"
    exit 1
fi

# Check if session already exists
if [ -f sessions/user.session ]; then
    echo -e "${YELLOW}⚠️  WARNING: Session file already exists${NC}"
    echo ""
    echo "File: sessions/user.session"
    echo ""
    read -p "Do you want to recreate it? This will log out the existing session. (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    echo ""
    echo "Removing old session..."
    rm -f sessions/user.session
    rm -f sessions/user.session-journal
fi

# Create sessions directory if it doesn't exist
mkdir -p sessions

echo -e "${BLUE}Building Docker image (this may take a minute)...${NC}"
docker compose build telebrief

echo ""
echo -e "${GREEN}Starting interactive session creation...${NC}"
echo ""
echo "You will be prompted for:"
echo "  1. Your phone number (international format: +1234567890)"
echo "  2. Verification code (sent to your Telegram app)"
echo "  3. 2FA password (if you have it enabled)"
echo ""
echo "======================================================================"
echo ""

# Run Docker container interactively to create session
docker run --rm -it \
    --env-file .env \
    -v "$(pwd)/sessions:/app/sessions" \
    -v "$(pwd)/.env:/app/.env:ro" \
    telebrief:latest \
    python create_session.py

RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}======================================================================"
    echo "  Session file created successfully!"
    echo "======================================================================${NC}"
    echo ""
    echo "File location: $(pwd)/sessions/user.session"
    echo ""
    echo -e "${GREEN}✅ You can now run:${NC}"
    echo "     docker compose up -d"
    echo ""
else
    echo ""
    echo -e "${RED}======================================================================"
    echo "  Session creation failed"
    echo "======================================================================${NC}"
    echo ""
    echo "Common issues:"
    echo "  - Wrong API credentials in .env"
    echo "  - Invalid phone number format (use +1234567890)"
    echo "  - Wrong verification code"
    echo ""
    echo "Try again: ./create_session.sh"
    echo ""
fi

exit $RESULT