from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class FileChange:
    path: str
    additions: int
    deletions: int

@dataclass
class Commit:
    hash: str
    date: str
    author_name: str
    author_email: str
    message: str
    files: list[FileChange]
    date_obj: datetime | None = None

