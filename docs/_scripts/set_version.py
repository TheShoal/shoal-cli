import tomllib
from pathlib import Path


def on_config(config, **kwargs):
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            version = tomllib.load(f)["project"]["version"]
            config["site_name"] = f"{config.get('site_name', 'Shoal')} v{version}"
    return config
