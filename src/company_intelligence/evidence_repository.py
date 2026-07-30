"""Filesystem persistence for versioned company evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from .evidence_registry import RegisteredEvidence
from .models import EvidenceItem


class EvidenceRepository:
    """Append-only JSON repository with symbol/category/date partitioning."""

    def __init__(self, root: str | Path = "company_data") -> None:
        self.root = Path(root)

    def save(self, record: RegisteredEvidence) -> Path:
        observed = record.item.as_of_date
        year, month, _ = observed.split("-")
        category = record.item.category.lower()
        directory = self.root / record.symbol / "evidence" / year / month
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{category}_{record.evidence_id[:16]}.json"
        if path.exists():
            raise FileExistsError(f"Evidence record already exists: {path}")

        payload = {
            **record.to_dict(),
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": "company_evidence_v1",
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def load_all(self, symbol: str | None = None) -> tuple[RegisteredEvidence, ...]:
        base = self.root
        if symbol is not None:
            base = base / symbol.strip().upper()
        if not base.exists():
            return ()

        records: list[RegisteredEvidence] = []
        for path in sorted(base.glob("**/evidence/**/*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            item = EvidenceItem(**raw["item"])
            records.append(
                RegisteredEvidence(
                    symbol=raw["symbol"],
                    evidence_id=raw["evidence_id"],
                    item=item,
                )
            )
        return tuple(records)

    def save_many(self, records: Iterable[RegisteredEvidence]) -> tuple[Path, ...]:
        return tuple(self.save(record) for record in records)
