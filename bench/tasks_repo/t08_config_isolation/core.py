DEFAULTS = {'retry': 3, 'labels': [], 'network': {'timeout': 10, 'ports': [80]}}
def load_config(overrides=None):
    config = DEFAULTS.copy()
    config.update(overrides or {})
    return config
def config_summary(config):
    return f"retry={config['retry']}"
