"""Journal des modifications : chaque changement enregistre son état AVANT pour pouvoir être annulé."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_path() -> Path:
    base = os.environ.get("ANDROID_PILOT_HOME") or Path.home() / ".android-pilot"
    return Path(base) / "journal.jsonl"


@dataclass
class Change:
    kind: str                 # package | setting | appop | standby
    target: str               # ex. "com.samsung.android.bixby.agent" ou "global/animator_duration_scale"
    before: str | None
    after: str | None
    undo: list[list[str]]     # liste d'argv shell à rejouer pour annuler
    note: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    ts: float = field(default_factory=time.time)
    rolled_back: bool = False


class Journal:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[Change]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Change(**json.loads(line)))
        return out

    def _save(self, changes: list[Change]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in changes), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, change: Change) -> Change:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(change), ensure_ascii=False) + "\n")
        return change

    def list(self, include_rolled_back: bool = False) -> list[Change]:
        return [c for c in self._load() if include_rolled_back or not c.rolled_back]

    def get(self, change_id: str) -> Change:
        for c in self._load():
            if c.id == change_id:
                return c
        raise KeyError(f"Changement {change_id} introuvable")

    def mark_rolled_back(self, change_id: str) -> None:
        changes = self._load()
        for c in changes:
            if c.id == change_id:
                c.rolled_back = True
        self._save(changes)
