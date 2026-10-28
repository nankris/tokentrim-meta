import unittest
from codec import encode, decode, hex_preview
from stream import FrameReader
class FrameTests(unittest.TestCase):
    def test_codec(self):
        self.assertEqual(encode(b'ab'),b'\x00\x02ab\xc3')
        self.assertEqual(encode(b''),b'\x00\x00\x00')
        for payload in (b'',b'\xff\x02',b'x'*65535):
            self.assertEqual(decode(encode(payload)),payload)
        with self.assertRaises(ValueError): encode(b'x'*65536)
        for frame in (b'',b'\x00',b'\x00\x00',b'\x00\x00\x01',b'\x00\x02ab\x00',encode(b'a')+b'x'):
            with self.subTest(frame=frame), self.assertRaises(ValueError): decode(frame)
        self.assertEqual(hex_preview(b'ab'),'6162')
    def test_every_split(self):
        wire = encode(b'one')+encode(b'')+encode(b'two')
        for split in range(len(wire)+1):
            reader = FrameReader()
            self.assertEqual(reader.feed(wire[:split])+reader.feed(wire[split:]),[b'one',b'',b'two'])
            self.assertIsNone(reader.finish())
        reader = FrameReader()
        result = []
        for byte in wire: result.extend(reader.feed(bytes([byte])))
        self.assertEqual(result,[b'one',b'',b'two'])
    def test_truncation_and_recovery(self):
        reader = FrameReader()
        self.assertEqual(reader.feed(b'\x00'),[])
        with self.assertRaises(ValueError): reader.finish()
        self.assertEqual(reader.feed(b'\x00\x00'),[b''])
        with self.assertRaises(ValueError): reader.feed(b'\x00\x00\x01' + encode(b'ignored'))
        self.assertEqual(reader.feed(encode(b'fresh')),[b'fresh'])
        self.assertEqual(reader.feed(b''),[])

if __name__ == "__main__":
    unittest.main()
