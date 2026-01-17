#!/usr/bin/env python3
"""
Create Telegram session using QR code or Phone number.
"""

import asyncio
import os
import sys
from pathlib import Path

import qrcode
from dotenv import load_dotenv
from telethon import TelegramClient


async def create_session():
    """Create Telegram session interactively."""
    print("=" * 70)
    print("Telegram Session Creator")
    print("=" * 70)
    print()

    # Load environment variables
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        print("❌ ERROR: Missing Telegram credentials")
        print()
        print("Please ensure your .env file contains:")
        print("  TELEGRAM_API_ID=your_api_id")
        print("  TELEGRAM_API_HASH=your_api_hash")
        print()
        print("Get these from: https://my.telegram.org")
        sys.exit(1)

    # Create sessions directory if it doesn't exist
    sessions_dir = Path("sessions")
    sessions_dir.mkdir(exist_ok=True)

    print(f"API ID: {api_id}")
    print(f"Session file: sessions/user.session")
    print()

    # Create client
    client = TelegramClient("sessions/user", int(api_id), api_hash)

    try:
        print("Connecting to Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            print()
            print("Select authentication method:")
            print("1. QR Code (Recommended - requires mobile app)")
            print("2. Phone Number (requires SMS/Code)")
            
            choice = input("\nEnter choice (1 or 2): ").strip()

            if choice == "1":
                print("\nGenerating QR Code...")
                qr = await client.qr_login()
                
                # Show QR code
                print("\n" + "=" * 50)
                print("SCAN THIS QR CODE WITH YOUR TELEGRAM APP")
                print("Settings -> Devices -> Link Desktop Device")
                print("=" * 50 + "\n")
                
                # Display QR code in terminal
                qr_url = qr.url
                qr_console = qrcode.QRCode()
                qr_console.add_data(qr_url)
                qr_console.print_ascii(invert=True)
                
                print("\nWaiting for login...")
                # Wait for login
                await qr.wait()
                
            else:
                print("\nYou will be prompted for:")
                print("  1. Your phone number (international format: +1234567890)")
                print("  2. Verification code")
                print()
                phone = input("Please enter your phone (or bot token): ")
                await client.start(phone=phone)

        print("-" * 70)
        print()
        print("✅ SUCCESS! Session created successfully")
        print()
        print(f"Session file: {sessions_dir / 'user.session'}")
        print()

        # Test the connection
        me = await client.get_me()
        print()
        print(f"Authenticated as: {me.first_name}")
        if me.username:
            print(f"Username: @{me.username}")
        print(f"Phone: {me.phone}")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Session creation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error creating session: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print()
    asyncio.run(create_session())
