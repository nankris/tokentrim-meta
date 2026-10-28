from dataclasses import dataclass
@dataclass
class Settings:
    timeout: float = 30.0
    retries: int = 3
def load_settings(mapping):
    return Settings()
def describe(settings):
    return f'timeout={settings.timeout:g}; retries={settings.retries}'
