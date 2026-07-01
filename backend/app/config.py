import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"   # un .json por proyecto
MEDIA_DIR = DATA_DIR / "media"         # imágenes y videos descargados

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# --- Playwright / Veo3 ---
# Perfil persistente de Chromium para no tener que loguearse cada vez.
CHROME_USER_DATA_DIR = os.getenv(
    "CHROME_USER_DATA_DIR", str(BASE_DIR / "chrome_profile")
)
# "chrome" usa tu instalación real de Google Chrome (más difícil de detectar
# como bot que el Chromium que instala `playwright install`). Necesita tener
# Chrome instalado en el sistema.
CHROME_CHANNEL = os.getenv("CHROME_CHANNEL", "chrome")
VEO3_URL = os.getenv("VEO3_URL", "https://labs.google/fx/es/tools/flow")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

# Timeouts (ms)
GENERATION_TIMEOUT_MS = int(os.getenv("GENERATION_TIMEOUT_MS", "180000"))  # 3 min
