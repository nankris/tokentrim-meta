# Stable Priority

PriorityQueue.push(priority, item) must accept arbitrary payloads, including dicts. pop() returns the lowest-priority payload, with FIFO order among equal priorities. len(queue) tracks pending items; an empty pop raises IndexError. Payloads must never need to be comparable.

Run `python -m unittest discover -s tests -q` from this directory.
