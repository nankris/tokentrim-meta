from dataclasses import dataclass
@dataclass
class Record:
    id: int
    text: str
def record_count(records): return len(records)
