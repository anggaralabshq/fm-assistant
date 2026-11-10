import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIX / name).read_text())
