from dataclasses import dataclass, field
@dataclass
class Record:
    id: int
    text: str
    tags: list = field(default_factory=list)
    def __post_init__(self):
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
def record_count(records): return len(records)
