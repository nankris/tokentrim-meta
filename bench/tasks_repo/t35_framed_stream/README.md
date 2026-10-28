# Framed Stream

Upgrade the byte protocol in codec.py and stream.py. A frame is a two-byte unsigned big-endian payload length, the payload (0..65535 bytes), then a one-byte checksum equal to sum(payload)%256. encode(payload) returns a frame and rejects oversized payloads with ValueError. decode(frame) requires exactly one complete frame and validates length/checksum, otherwise ValueError. FrameReader.feed(chunk) accepts arbitrary byte chunks, buffers incomplete data, and returns all newly completed payloads in order (including empty payloads); finish() raises ValueError for a truncated tail and otherwise returns None. A malformed completed frame clears buffered data and raises ValueError; the reader must then accept a fresh valid stream. Returned payloads are bytes.

Run `python -m unittest discover -s tests -q` from this directory.
