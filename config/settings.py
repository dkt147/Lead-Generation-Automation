"""
Configuration Management Module
Loads and validates environment variables for all API integrations.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class MondayConfig:
    """Monday.com API configuration"""
    api_key: str
    board_id: str = ""
    api_url: str = "https://api.monday.com/v2"


@dataclass
class GroqConfig:
    """Groq API configuration"""
    api_key: str
    model: str = "llama-3.3-70b-versatile"
    api_url: str = "https://api.groq.com/openai/v1"


@dataclass
class HunterConfig:
    """Hunter.io API configuration"""
    api_key: str
    api_url: str = "https://api.hunter.io/v2"


@dataclass
class EmailConfig:
    """Gmail SMTP configuration"""
    address: str
    app_password: str
    sender_name: str
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587


@dataclass
class AppConfig:
    """Main application configuration"""
    monday: MondayConfig
    groq: GroqConfig
    hunter: HunterConfig
    email: EmailConfig
    default_company_count: int = 10
    default_region: str = "Winnipeg, Manitoba"


def load_config() -> AppConfig:
    """Load configuration from environment variables"""

    # Validate required environment variables
    required_vars = [
        "MONDAY_API_KEY",
        "GROQ_API_KEY",
        "HUNTER_API_KEY",
        "GMAIL_ADDRESS",
        "GMAIL_APP_PASSWORD"
    ]

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return AppConfig(
        monday=MondayConfig(
            api_key=os.getenv("MONDAY_API_KEY"),
            board_id=os.getenv("MONDAY_BOARD_ID", "")
        ),
        groq=GroqConfig(
            api_key=os.getenv("GROQ_API_KEY")
        ),
        hunter=HunterConfig(
            api_key=os.getenv("HUNTER_API_KEY")
        ),
        email=EmailConfig(
            address=os.getenv("GMAIL_ADDRESS"),
            app_password=os.getenv("GMAIL_APP_PASSWORD"),
            sender_name=os.getenv("SENDER_NAME", "Lead Generator")
        ),
        default_company_count=int(os.getenv("DEFAULT_COMPANY_COUNT", "10")),
        default_region=os.getenv("DEFAULT_REGION", "Winnipeg, Manitoba")
    )


# Singleton config instance
_config = None


def get_config() -> AppConfig:
    """Get the application configuration (singleton pattern)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config