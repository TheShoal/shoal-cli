import re
import tomllib
from pathlib import Path


def on_config(config, **kwargs):
    # Prefer __init__.py (works with both static and dynamic versioning in pyproject.toml)
    init_path = Path("src/shoal/__init__.py")
    if init_path.exists():
        match = re.search(r'__version__\s*=\s*"([^"]+)"', init_path.read_text())
        if match:
            config["site_name"] = f"{config.get('site_name', 'Shoal')} v{match.group(1)}"
            return config
    # Fallback: static version in pyproject.toml
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            version = data["project"].get("version")
            if version:
                config["site_name"] = f"{config.get('site_name', 'Shoal')} v{version}"
    return config
