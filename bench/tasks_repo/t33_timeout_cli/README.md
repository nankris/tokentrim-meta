# Timeout Cli

Wire configurable request timeouts through settings.py and cli.py. load_settings(mapping) returns a Settings whose timeout defaults to 30.0; accept numeric values or numeric strings strictly greater than zero and finite, otherwise ValueError (including bool). parse_cli(argv, defaults=None) returns Settings, using defaults as the settings mapping, with an optional --timeout VALUE overriding it. Last repeated option wins. Missing values or unknown arguments raise ValueError. Keep Settings.retries=3 and describe() output working. Both direct loading and CLI overrides must use the same timeout validation.

Run `python -m unittest discover -s tests -q` from this directory.
