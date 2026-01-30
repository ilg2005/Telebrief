"""
Configuration loader for Telebrief.
Loads settings from config.yaml and environment variables.
"""

import os
from dataclasses import dataclass
from typing import List

import yaml
from dotenv import load_dotenv

from src.runtime_settings import DEFAULT_RUNTIME_SETTINGS_PATH, load_runtime_settings


@dataclass
class ChannelConfig:
    """Configuration for a single Telegram channel/chat."""

    id: str
    name: str


@dataclass
class Settings:
    """Application settings."""

    schedule_time: str
    timezone: str
    enable_scheduler: bool
    lookback_hours: int
    openai_model: str
    default_openai_model: str
    openai_temperature: float
    max_tokens_per_summary: int
    use_emojis: bool
    include_statistics: bool
    target_user_id: int
    auto_cleanup_old_digests: bool
    max_messages_per_channel: int
    api_timeout: int


@dataclass
class Config:
    """Complete application configuration."""

    channels: List[ChannelConfig]
    settings: Settings

    # Environment variables
    telegram_api_id: int
    telegram_api_hash: str
    telegram_bot_token: str
    openai_api_key: str
    openai_base_url: str
    log_level: str


def _coerce_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def load_config(config_path: str = "config.yaml") -> Config:
    """
    Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to config.yaml file

    Returns:
        Config object with all settings

    Raises:
        FileNotFoundError: If config.yaml not found
        ValueError: If required environment variables missing
    """
    # Load environment variables from .env file
    load_dotenv()

    # Load YAML configuration
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        yaml_config = yaml.safe_load(f)

    # Parse channels
    channels = [
        ChannelConfig(id=ch["id"], name=ch["name"]) for ch in yaml_config.get("channels", [])
    ]

    if not channels:
        raise ValueError("No channels configured in config.yaml")

    # Parse settings
    settings_dict = yaml_config.get("settings", {})
    runtime_settings_path = os.getenv(
        "TELEBRIEF_RUNTIME_SETTINGS_PATH", DEFAULT_RUNTIME_SETTINGS_PATH
    )
    runtime_settings = load_runtime_settings(runtime_settings_path)

    openai_model_env = os.getenv("OPENAI_MODEL")
    default_openai_model = openai_model_env or settings_dict.get("openai_model", "gpt-5-nano")
    runtime_openai_model = runtime_settings.get("openai_model")
    effective_openai_model = (
        runtime_openai_model if isinstance(runtime_openai_model, str) and runtime_openai_model.strip() else default_openai_model
    )

    settings = Settings(
        schedule_time=settings_dict.get("schedule_time", "08:00"),
        timezone=settings_dict.get("timezone", "UTC"),
        enable_scheduler=_coerce_bool(
            runtime_settings.get("enable_scheduler"),
            _coerce_bool(settings_dict.get("enable_scheduler"), True),
        ),
        lookback_hours=settings_dict.get("lookback_hours", 24),
        openai_model=effective_openai_model,
        default_openai_model=default_openai_model,
        openai_temperature=settings_dict.get("openai_temperature", 0.7),
        max_tokens_per_summary=settings_dict.get("max_tokens_per_summary", 500),
        use_emojis=settings_dict.get("use_emojis", True),
        include_statistics=settings_dict.get("include_statistics", True),
        target_user_id=settings_dict.get("target_user_id", 0),
        auto_cleanup_old_digests=settings_dict.get("auto_cleanup_old_digests", True),
        max_messages_per_channel=settings_dict.get("max_messages_per_channel", 500),
        api_timeout=settings_dict.get("api_timeout", 30),
    )

    if settings.target_user_id == 0:
        raise ValueError(
            "target_user_id not configured in config.yaml. "
            "Get your Telegram user ID from @userinfobot"
        )

    # Load environment variables
    telegram_api_id = os.getenv("TELEGRAM_API_ID")
    telegram_api_hash = os.getenv("TELEGRAM_API_HASH")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    log_level = os.getenv("LOG_LEVEL", "INFO")

    # Validate required environment variables
    missing_vars = []
    if not telegram_api_id:
        missing_vars.append("TELEGRAM_API_ID")
    if not telegram_api_hash:
        missing_vars.append("TELEGRAM_API_HASH")
    if not telegram_bot_token:
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    if not openai_api_key:
        missing_vars.append("OPENAI_API_KEY")

    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            f"Please set them in .env file (see .env.example)"
        )

    # Create complete config
    # Type assertions: variables are validated above
    assert telegram_api_id is not None
    assert telegram_api_hash is not None
    assert telegram_bot_token is not None
    assert openai_api_key is not None

    config = Config(
        channels=channels,
        settings=settings,
        telegram_api_id=int(telegram_api_id),
        telegram_api_hash=telegram_api_hash,
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        log_level=log_level,
    )

    return config


def add_channel_to_config_file(config_path: str, channel_id: int, channel_name: str) -> bool:
    """
    Add a channel to the config.yaml file preserving comments.
    
    Args:
        config_path: Path to config.yaml
        channel_id: Channel ID
        channel_name: Channel name
        
    Returns:
        True if successful
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Find "channels:" section
        channels_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("channels:"):
                channels_idx = i
                break
                
        if channels_idx == -1:
            return False
            
        # Find insertion point (end of channels list)
        # We look for the start of the next section (no indentation)
        # or end of file
        insert_idx = len(lines)
        
        for i in range(channels_idx + 1, len(lines)):
            line = lines[i]
            # Check for non-empty, non-comment line with 0 indentation
            if line.strip() and not line.strip().startswith("#") and not line.startswith(" "):
                insert_idx = i
                break
                
        # Prepare new entry lines
        new_entry = [
            f"  - id: {channel_id}\n",
            f"    name: \"{channel_name}\"\n"
        ]
        
        # Insert
        lines[insert_idx:insert_idx] = new_entry
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        return True
        
    except Exception as e:
        print(f"Error updating config: {e}")
        return False


def remove_channel_from_config_file(config_path: str, channel_id: int) -> bool:
    """
    Remove a channel from the config.yaml file.
    
    Args:
        config_path: Path to config.yaml
        channel_id: Channel ID to remove
        
    Returns:
        True if successful
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Find "channels:" section
        channels_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("channels:"):
                channels_idx = i
                break
                
        if channels_idx == -1:
            return False
            
        # Find the channel entry
        start_idx = -1
        end_idx = -1
        
        # Look for "- id: CHANNEL_ID"
        target_str = str(channel_id)
        
        for i in range(channels_idx + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()
            
            # Start of a channel block
            if stripped.startswith("- id:"):
                # If we found the start of our target channel
                if target_str in stripped:
                    start_idx = i
                # If we were tracking a channel and found a NEW one, that's the end
                elif start_idx != -1:
                    end_idx = i
                    break
            
            # If we hit a new top-level section (no indentation) or end of file
            elif start_idx != -1 and stripped and not line.startswith(" ") and not line.startswith("#"):
                end_idx = i
                break

        # If we found start but not end, it means it goes until EOF
        if start_idx != -1 and end_idx == -1:
            end_idx = len(lines)
            
        if start_idx == -1:
            print(f"Channel ID {channel_id} not found in config")
            return False
            
        # Remove lines
        del lines[start_idx:end_idx]
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
        return True
        
    except Exception as e:
        print(f"Error removing from config: {e}")
        return False


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = load_config()
        print("✅ Configuration loaded successfully!")
        print(f"Channels: {len(config.channels)}")
        print(f"Target user: {config.settings.target_user_id}")
        print(f"Model: {config.settings.openai_model}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
