from dataclasses import dataclass
import math
@dataclass
class Settings:
    timeout: float = 30.0
    retries: int = 3
def load_settings(mapping):
    raw = mapping.get('timeout',30.0)
    if isinstance(raw,bool): raise ValueError('invalid timeout')
    try: timeout = float(raw)
    except (TypeError,ValueError): raise ValueError('invalid timeout') from None
    if not math.isfinite(timeout) or timeout <= 0: raise ValueError('invalid timeout')
    return Settings(timeout=timeout)
def describe(settings):
    return f'timeout={settings.timeout:g}; retries={settings.retries}'
