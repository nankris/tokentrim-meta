import unittest
from core import load_config, DEFAULTS
from copy import deepcopy
class ConfigTests(unittest.TestCase):
    def test_defaults_isolated(self):
        saved = deepcopy(DEFAULTS)
        try:
            first = load_config()
            first['network']['ports'].append(443)
            first['labels'].append('x')
            self.assertEqual(DEFAULTS, saved)
            self.assertEqual(load_config(), saved)
        finally:
            DEFAULTS.clear(); DEFAULTS.update(saved)
    def test_override_isolated_and_replaced(self):
        overrides = {'network': {'ports': []}, 'retry':0, 'extra':[{'x':1}]}
        config = load_config(overrides)
        self.assertEqual(config['network'], {'ports':[]})
        self.assertEqual(config['retry'],0)
        config['extra'][0]['x'] = 2
        self.assertEqual(overrides['extra'][0]['x'],1)
        overrides['network']['ports'].append(2)
        self.assertEqual(config['network']['ports'],[])

if __name__ == "__main__":
    unittest.main()
