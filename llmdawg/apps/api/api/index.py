import sys
import os

# Make src/ importable — Vercel runs from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llmdawg_api.main import create_app  # noqa: E402

app = create_app()
