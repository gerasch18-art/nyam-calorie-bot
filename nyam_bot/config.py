import logging
import os
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

DATABASE_URL = os.getenv("DATABASE_URL", "")

FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "10"))
PRO_DAILY_LIMIT = int(os.getenv("PRO_DAILY_LIMIT", "50"))

STORAGE_TYPE = os.getenv("STORAGE_TYPE", "memory")

BASE_DIR = Path(__file__).parent