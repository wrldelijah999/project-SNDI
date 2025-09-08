import yaml
from pathlib import Path
from sndi.storage import resource_path

def load_config() -> dict:
    candidates = [
        resource_path("config.yaml"),
        resource_path("assets/config.yaml"),
    ]
    for p in candidates:
        cp = Path(p)
        if cp.exists():
            with open(cp, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("Config file not found in: " + " | ".join(candidates))
