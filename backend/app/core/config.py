from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path

# Set the base directory to the project root
# This allows the .env file to be found consistently
# whether running from the root or from within the backend directory.
_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE_PATH = _BASE_DIR / '.env'

class Settings(BaseSettings):
    """
    Application settings loaded from .env file or environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATH, 
        env_file_encoding='utf-8', 
        extra='ignore'
    )
    
    # --- Gemini API Key ---
    # Your Google AI Studio API Key
    GEMINI_API_KEY: str = ""

    # --- Mistral API Key ---
    # Your Mistral AI API Key for OCR and other tasks
    MISTRAL_API_KEY: str = ""

settings = Settings()

# Log whether the .env file was loaded successfully
if os.path.exists(_ENV_FILE_PATH):
    print(f"Loaded settings from: {_ENV_FILE_PATH}")
else:
    print(f"Warning: .env file not found at {_ENV_FILE_PATH}. Using default settings or environment variables.") 