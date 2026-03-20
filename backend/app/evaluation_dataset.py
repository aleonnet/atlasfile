from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .classifier_registry import classifier_state_root
from .config import settings
from .utils import sha256_file, utc_now_iso


def classifier_datasets_root() -> Path:
    configured = str(os.environ.get("CLASSIFIER_DATASETS_ROOT") or getattr(settings, "classifier_datasets_root", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return classifier_state_root() / "datasets"


def validation_set_root() -> Path:
    return classifier_datasets_root() / "validation_set"


def validation_set_files_dir() -> Path:
    return validation_set_root() / "files"


def validation_set_expected_path() -> Path:
    return validation_set_root() / "expected.json"


def training_pool_root() -> Path:
    return classifier_datasets_root() / "training_pool"


def training_pool_records_path() -> Path:
    return training_pool_root() / "records.jsonl"


def training_pool_files_dir() -> Path:
    return training_pool_root() / "files"


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
    source_path: str = ""
    business_domain: str
    document_type: str
    decision: str
    sha256: str = ""
    reviewed_at: str = Field(default_factory=utc_now_iso)
    topics: list[str] = Field(default_factory=list)
    entities: list[ValidationEntity] = Field(default_factory=list)
    notes: str = ""


def _normalize_training_pool_record(record: TrainingPoolRecord) -> TrainingPoolRecord:
    raw_path = str(record.path or "").strip()
    if not raw_path:
        return record
    file_name = Path(raw_path).name
    if not file_name:
        return record
    operational_path = training_pool_files_dir() / file_name
    if not operational_path.exists():
        return record
    normalized_path = dataset_relative_path(operational_path)
    if raw_path == normalized_path:
        return record
    return record.model_copy(update={"path": normalized_path})


def ensure_dataset_scaffold() -> None:
    classifier_datasets_root().mkdir(parents=True, exist_ok=True)
    validation_set_root().mkdir(parents=True, exist_ok=True)
    validation_set_files_dir().mkdir(parents=True, exist_ok=True)
    training_pool_root().mkdir(parents=True, exist_ok=True)
    training_pool_files_dir().mkdir(parents=True, exist_ok=True)
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
        raise ValueError("validation_set/expected.json deve ser uma lista JSON")
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
    normalized = False
    for line in training_pool_records_path().read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        record = TrainingPoolRecord.model_validate_json(payload)
        updated = _normalize_training_pool_record(record)
        normalized = normalized or updated.path != record.path
        records.append(updated)
    if normalized:
        save_training_pool_records(records)
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


def validation_sha_index() -> dict[str, list[str]]:
    ensure_dataset_scaffold()
    index: dict[str, list[str]] = {}
    for entry in load_validation_set():
        if not entry.is_labeled():
            continue
        file_path = resolve_validation_file(entry.file)
        if not file_path.exists():
            continue
        digest = sha256_file(file_path)
        index.setdefault(digest, []).append(entry.file)
    return index


def validation_overlap_for_file(file_path: Path) -> list[str]:
    if not file_path.exists() or not file_path.is_file():
        return []
    return sorted(validation_sha_index().get(sha256_file(file_path), []))


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


def _training_pool_snapshot_name(doc_id: str, original_filename: str, fallback_name: str) -> str:
    filename = Path(original_filename or fallback_name or "documento.bin").name
    return f"{doc_id}__{filename}"


def dataset_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(classifier_datasets_root().resolve()))
    except ValueError:
        return str(path)


def materialize_training_pool_snapshot(
    *,
    source_path: Path,
    doc_id: str,
    original_filename: str,
) -> tuple[Path, str]:
    ensure_dataset_scaffold()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(source_path)

    digest = sha256_file(source_path)
    snapshot_name = _training_pool_snapshot_name(doc_id, original_filename, source_path.name)
    snapshot_path = training_pool_files_dir() / snapshot_name

    for stale in training_pool_files_dir().glob(f"{doc_id}__*"):
        if stale != snapshot_path and stale.is_file():
            stale.unlink(missing_ok=True)

    if snapshot_path.exists() and sha256_file(snapshot_path) == digest:
        return snapshot_path, digest

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, snapshot_path)
    return snapshot_path, digest


def append_training_pool_record(record: TrainingPoolRecord) -> None:
    ensure_dataset_scaffold()
    with training_pool_records_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
