import os
try:
    import tomllib
except ImportError:
    tomllib = None

DEFAULT_SETTINGS_PATH = "settings.toml"
EXAMPLE_SETTINGS_PATH = "settings.example.toml"


def load_settings(path: str = DEFAULT_SETTINGS_PATH) -> dict:
    """
    Load settings from a TOML file.

    Tries to load from the specified path first, then falls back to
    the example settings file if the primary one is not found.
    Returns an empty dictionary if neither can be loaded.
    """
    if not tomllib:
        print("Warning: tomllib is not available. Install with 'pip install tomli' for Python < 3.11.")
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        print(f"Warning: '{path}' not found. Falling back to example settings.")
        try:
            with open(EXAMPLE_SETTINGS_PATH, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            print(f"Warning: Example settings '{EXAMPLE_SETTINGS_PATH}' also not found. Using empty config.")
            return {}
    except Exception as e:
        print(f"Error loading settings from '{path}': {e}")
        return {}

# Load settings once and make them available
settings = load_settings()
