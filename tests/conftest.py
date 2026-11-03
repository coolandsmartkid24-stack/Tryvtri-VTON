import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root and src to sys.path
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from backend.app.config import reset_settings_cache
reset_settings_cache()
