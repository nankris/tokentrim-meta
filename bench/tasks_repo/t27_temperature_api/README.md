# Temperature Api

Unify the temperature conversions behind convert(value, source, target), supporting case-insensitive C, F and K codes. Keep c_to_f and f_to_c callable with their existing results, and have them use the shared conversion behavior. Add Kelvin support and identity conversions. Unknown units raise ValueError. Do not reject negative temperatures or round outputs.

Run `python -m unittest discover -s tests -q` from this directory.
