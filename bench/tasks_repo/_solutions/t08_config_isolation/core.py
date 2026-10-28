from copy import deepcopy
DEFAULTS = {'retry': 3, 'labels': [], 'network': {'timeout': 10, 'ports': [80]}}
def load_config(overrides=None):
    config = deepcopy(DEFAULTS)
    if overrides is not None: config.update(deepcopy(overrides))
    return config
def config_summary(config):
    return f"retry={config['retry']}"
