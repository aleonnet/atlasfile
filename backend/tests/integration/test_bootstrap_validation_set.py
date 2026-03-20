from __future__ import annotations

import json
import os
from pathlib import Path

from app.classification_bootstrap import classify_bootstrap
from app.document_extractor import extract_document_content
from app.evaluation_dataset import load_validation_set, resolve_validation_file
from app.profile_schema_v2 import ProjectProfileV2
from app.project_profile import profile_v2_to_runtime


CURRENT_VALIDATION_FILES = {
    "20220824_Kickoff_Neptune_V2.3.pptx",
    "CT 4600052462_Contrato_Servicos_TI.pdf",
    "CW2249236_-_4600052462_-_1º_Aditivo_Projeto_S.pdf",
    "DocuSign_Project_Neptune___SPA__Anexos_v_A.pdf",
    "Fato Relevante-Proposta Vinculante Sites de Infraestrutura de Telecomunicações Fixa.pdf",
    "FATO RELEVANTE_Oferta Vinculante Torres_Venus.pdf",
    "Neptune_Milestones e Estimativa de Esforço_22.08.09 1359[76]  -  Read-Only.pdf",
    "Processo de Pgtos Lemvig_v05_24.03.2023.pptx",
    "Project Neptune _ 1o Aditamento SPA e Anexos_v. Assinada.pdf",
    "Project Neptune _ MLA Inicial e Anexos_v. Assinada.pdf",
    "Project Neptune _ TSA_v. Assinada.pdf",
    "RES Projeto Saturno  Carga de Ativos.msg",
}


def _load_default_profile() -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    template_path = repo_root / "config" / "templates" / "default.json"
    raw = json.loads(template_path.read_text(encoding="utf-8"))
    raw.setdefault("project_id", "validation_set")
    raw.setdefault("project_label", "Validation Set")
    raw.setdefault("project_root", str(repo_root / "config" / "validation_set"))
    profile = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(profile, Path(profile.project_root))


def _fixture_dataset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "classifier_datasets"


def test_bootstrap_quality_floor_for_current_12_files() -> None:
    fixture_root = _fixture_dataset_root()
    previous_root = os.environ.get("CLASSIFIER_DATASETS_ROOT")
    os.environ["CLASSIFIER_DATASETS_ROOT"] = str(fixture_root)
    try:
        profile = _load_default_profile()
        entries = [entry for entry in load_validation_set() if entry.file in CURRENT_VALIDATION_FILES]

        assert {entry.file for entry in entries} == CURRENT_VALIDATION_FILES

        document_type_hits = 0
        business_domain_hits = 0

        for entry in entries:
            file_path = resolve_validation_file(entry.file)
            extracted = extract_document_content(file_path, max_chars=50_000)
            result = classify_bootstrap(
                profile=profile,
                source_path=file_path,
                text_excerpt=extracted.text_excerpt,
            )
            if result["document_type"] == entry.document_type:
                document_type_hits += 1
            if result["business_domain"] == entry.business_domain:
                business_domain_hits += 1

        assert document_type_hits == len(entries)
        assert business_domain_hits >= 9
    finally:
        if previous_root is None:
            os.environ.pop("CLASSIFIER_DATASETS_ROOT", None)
        else:
            os.environ["CLASSIFIER_DATASETS_ROOT"] = previous_root
