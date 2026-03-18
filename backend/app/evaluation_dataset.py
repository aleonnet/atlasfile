from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .utils import utc_now_iso


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def validation_set_root() -> Path:
    return repo_root() / "config" / "validation_set"


def validation_set_files_dir() -> Path:
    return validation_set_root() / "files"


def validation_set_expected_path() -> Path:
    return validation_set_root() / "expected.json"


def training_pool_root() -> Path:
    return repo_root() / "config" / "training_pool"


def training_pool_records_path() -> Path:
    return training_pool_root() / "records.jsonl"


class ValidationEntity(BaseModel):
    type: str
    value: str


class ValidationSetEntry(BaseModel):
    file: str
    document_type: str = ""
    business_domain: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[ValidationEntity] = Field(default_factory=list)
    notes: str = ""

    def is_labeled(self) -> bool:
        return bool(self.document_type.strip() and self.business_domain.strip())


class TrainingPoolRecord(BaseModel):
    doc_id: str
    project_id: str
    original_filename: str
    path: str
    business_domain: str
    document_type: str
    decision: str
    reviewed_at: str = Field(default_factory=utc_now_iso)
    topics: list[str] = Field(default_factory=list)
    entities: list[ValidationEntity] = Field(default_factory=list)
    notes: str = ""


def ensure_dataset_scaffold() -> None:
    validation_set_root().mkdir(parents=True, exist_ok=True)
    validation_set_files_dir().mkdir(parents=True, exist_ok=True)
    training_pool_root().mkdir(parents=True, exist_ok=True)
    expected_path = validation_set_expected_path()
    if not expected_path.exists():
        expected_path.write_text("[]\n", encoding="utf-8")
    records_path = training_pool_records_path()
    if not records_path.exists():
        records_path.write_text("", encoding="utf-8")


def load_validation_set() -> list[ValidationSetEntry]:
    ensure_dataset_scaffold()
    raw = json.loads(validation_set_expected_path().read_text(encoding="utf-8") or "[]")
    if not isinstance(raw, list):
        raise ValueError("config/validation_set/expected.json deve ser uma lista JSON")
    return [ValidationSetEntry.model_validate(item) for item in raw]


def save_validation_set(entries: list[ValidationSetEntry]) -> None:
    ensure_dataset_scaffold()
    payload = [entry.model_dump(mode="json") for entry in entries]
    validation_set_expected_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_training_pool_records() -> list[TrainingPoolRecord]:
    ensure_dataset_scaffold()
    records: list[TrainingPoolRecord] = []
    for line in training_pool_records_path().read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        records.append(TrainingPoolRecord.model_validate_json(payload))
    return records


def save_training_pool_records(records: list[TrainingPoolRecord]) -> None:
    ensure_dataset_scaffold()
    payload = "\n".join(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) for record in records)
    training_pool_records_path().write_text((payload + "\n") if payload else "", encoding="utf-8")


def sync_validation_entries_from_files() -> list[ValidationSetEntry]:
    ensure_dataset_scaffold()
    entries = {entry.file: entry for entry in load_validation_set()}
    for path in sorted(validation_set_files_dir().glob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name not in entries:
            entries[path.name] = ValidationSetEntry(file=path.name)
    ordered = [entries[name] for name in sorted(entries)]
    save_validation_set(ordered)
    return ordered


def resolve_validation_file(file_name: str) -> Path:
    return validation_set_files_dir() / file_name


def stage_validation_files(source_paths: Iterable[Path]) -> list[Path]:
    ensure_dataset_scaffold()
    staged: list[Path] = []
    for source in source_paths:
        if not source.exists() or not source.is_file():
            continue
        candidate = validation_set_files_dir() / source.name
        if candidate.exists() and candidate.resolve() != source.resolve():
            stem = source.stem
            suffix = source.suffix
            idx = 2
            candidate = validation_set_files_dir() / f"{stem}__{idx}{suffix}"
            while candidate.exists():
                idx += 1
                candidate = validation_set_files_dir() / f"{stem}__{idx}{suffix}"
        if not candidate.exists():
            shutil.copy2(source, candidate)
        staged.append(candidate)
    sync_validation_entries_from_files()
    return staged


def append_training_pool_record(record: TrainingPoolRecord) -> None:
    ensure_dataset_scaffold()
    with training_pool_records_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
