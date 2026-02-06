
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Try to import streamlit for secrets
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Load .env for local development
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)


def get_env(key: str, default: str = "") -> str:
    """Get environment variable from either Streamlit secrets or .env"""
    if HAS_STREAMLIT and hasattr(st, 'secrets'):
        # Try to get from Streamlit secrets first
        try:
            # Handle nested keys like "monday.api_key"
            parts = key.lower().split('_')
            if len(parts) >= 2:
                section = parts[0]
                field = '_'.join(parts[1:])
                
                # Map common patterns
                if section == "monday":
                    if field == "api_key":
                        return st.secrets["monday"]["api_key"]
                    elif field == "board_id":
                        return st.secrets["monday"]["board_id"]
                elif section == "groq":
                    if field == "api_key":
                        return st.secrets["groq"]["api_key"]
                elif section == "hunter":
                    if field == "api_key":
                        return st.secrets["hunter"]["api_key"]
                elif section == "gmail":
                    if field == "address":
                        return st.secrets["gmail"]["address"]
                    elif field == "app_password":
                        return st.secrets["gmail"]["app_password"]
                elif section == "sender":
                    if field == "name":
                        return st.secrets["gmail"].get("sender_name", default)
                elif section == "default":
                    if field == "company_count":
                        return str(st.secrets["defaults"].get("company_count", default))
                    elif field == "region":
                        return st.secrets["defaults"].get("region", default)
        except (KeyError, AttributeError):
            pass
    
    # Fallback to environment variables
    return os.getenv(key, default)


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
    """Load configuration from Streamlit secrets or environment variables"""
    # Get values using helper function
    monday_api_key = get_env("MONDAY_API_KEY")
    monday_board_id = get_env("MONDAY_BOARD_ID")
    groq_api_key = get_env("GROQ_API_KEY")
    hunter_api_key = get_env("HUNTER_API_KEY")
    gmail_address = get_env("GMAIL_ADDRESS")
    gmail_app_password = get_env("GMAIL_APP_PASSWORD")
    sender_name = get_env("SENDER_NAME", "Lead Generator")
    
    # Validate required variables
    required = {
        "MONDAY_API_KEY": monday_api_key,
        "GROQ_API_KEY": groq_api_key,
        "HUNTER_API_KEY": hunter_api_key,
        "GMAIL_ADDRESS": gmail_address,
        "GMAIL_APP_PASSWORD": gmail_app_password
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"For Streamlit Cloud: Add these in the Secrets section of your app settings.\n"
            f"For local dev: Check your .env file has all required keys."
        )
    
    return AppConfig(
        monday=MondayConfig(
            api_key=monday_api_key,
            board_id=monday_board_id
        ),
        groq=GroqConfig(
            api_key=groq_api_key
        ),
        hunter=HunterConfig(
            api_key=hunter_api_key
        ),
        email=EmailConfig(
            address=gmail_address,
            app_password=gmail_app_password,
            sender_name=sender_name
        ),
        default_company_count=int(get_env("DEFAULT_COMPANY_COUNT", "10")),
        default_region=get_env("DEFAULT_REGION", "Winnipeg, Manitoba")
    )


# Singleton config instance
_config = None


def get_config() -> AppConfig:
    """Get the application configuration (singleton pattern)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config
