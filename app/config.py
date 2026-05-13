import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DATABASE_URL = os.getenv("DATABASE_URL")

def validate_config() -> None:
    """Validate critical configuration on startup."""
    errors = []
    
    if not OPENROUTER_API_KEY:
        errors.append("OPENROUTER_API_KEY is not set. Please add it to .env file.")
    if not OPENROUTER_MODEL:
        errors.append("OPENROUTER_MODEL is not set. Please add it to .env file.")
    
    if errors:
        print("\n❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease check your .env file and restart the application.\n")
        sys.exit(1)
