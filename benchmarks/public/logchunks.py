"""LogChunks (Brandt, Panichella, Beller; MSR 2020; CC-BY-4.0; Zenodo 10.5281/zenodo.3632351 v1.0.0) loader + grader.

797 REAL failed Travis CI build logs; for each one a human labelled the log chunk that explains why the build
failed. TokenTrim use: the log is the tool output, the task is "quote the lines that explain the failure".
The data is NOT vendored in the repo; ``LOGCHUNKS_DIR`` points at the unzipped download (see DATA_SOURCES.md).
"""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(os.environ.get("LOGCHUNKS_DIR", "/workspace/pubdata/logchunks/LogChunks"))
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\[0K|\[[0-9;]{1,8}m")


def clean(text: str) -> str:
    """Strip ANSI colour codes and carriage-return overwrites (what a log viewer shows)."""
    text = ANSI.sub("", text.replace("\r\n", "\n"))
    return "\n".join(line.split("\r")[-1] for line in text.split("\n"))


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", clean(text)).strip().lower()


def examples():
    out = []
    for xml in sorted((ROOT / "build-failure-reason").glob("*/*.xml")):
        for ex in ET.parse(xml).getroot().iter("Example"):
            rel = ex.findtext("Log").strip()
            path = ROOT / "logs" / rel
            if not path.exists():
                continue
            out.append({"id": Path(rel).stem, "repo": rel.split("/")[1], "lang": rel.split("/")[0], "path": str(path),
                        "chunk": ex.findtext("Chunk") or "", "category": ex.findtext("Category"),
                        "keywords": [k.strip() for k in (ex.findtext("Keywords") or "").split(",") if k.strip()]})
    return out


def read_log(ex) -> str:
    return clean(Path(ex["path"]).read_text(encoding="utf-8", errors="replace"))


def key_lines(chunk: str, min_len: int = 6) -> list[str]:
    """Significant lines of the labelled chunk (normalised, de-duplicated, order kept)."""
    seen, out = set(), []
    for line in clean(chunk).split("\n"):
        n = norm(line)
        if len(n) >= min_len and not re.fullmatch(r"[\W_]+", n) and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def line_found(line: str, hay: str) -> bool:
    """A chunk line is found if it appears verbatim (normalised), or, for long lines, a 60-char prefix does
    (models often shorten long lines)."""
    return line in hay or (len(line) > 80 and line[:60] in hay)


def recall(chunk: str, text: str) -> float:
    lines = key_lines(chunk)
    if not lines:
        return 0.0
    hay = norm(text)
    return sum(line_found(l, hay) for l in lines) / len(lines)


def grade(answer: str, ex, threshold: float = 0.5):
    """Pre-registered metric: pass iff >= 50% of the chunk's significant lines appear in the answer."""
    r = recall(ex["chunk"], answer)
    return r >= threshold, r
