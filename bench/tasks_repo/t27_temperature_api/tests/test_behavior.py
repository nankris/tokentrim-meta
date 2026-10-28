import unittest
from core import convert, c_to_f, f_to_c, temperature_label
class TemperatureTests(unittest.TestCase):
    def test_legacy(self):
        self.assertEqual(c_to_f(0),32)
        self.assertAlmostEqual(f_to_c(212),100)
        self.assertEqual(c_to_f(-40),-40)
        self.assertEqual(temperature_label(2.25,'C'),'2.2 °C')
    def test_kelvin_and_identity(self):
        for value,source,target,expected in [(0,'c','K',273.15),(273.15,'K','c',0),(32,'F','K',273.15),(373.15,'k','f',212),(12.345,'K','K',12.345),(-300,'C','K',-26.85)]:
            with self.subTest(source=source,target=target): self.assertAlmostEqual(convert(value,source,target),expected)
        for source,target in [('X','C'),('C','X'),('X','X')]:
            with self.assertRaises(ValueError): convert(0,source,target)

if __name__ == "__main__":
    unittest.main()
