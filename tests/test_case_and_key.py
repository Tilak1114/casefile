import pytest
from pydantic import ValidationError

from casefile.config import DATA_DIR
from casefile.case import CaseConfig, FileAssignment, FileGroup
from casefile.evaluation.answer_key import AnswerKey

NTSB = {"page": "30", "quote": "a quote from the NTSB report"}


def case(*groups: FileGroup) -> CaseConfig:
    return CaseConfig(
        case_id="T1",
        title="test",
        event_date="2006-07-10",
        event_summary="test",
        files=[FileAssignment(file_no=i + 1, group=g, reason="test") for i, g in enumerate(groups)],
    )


def key(**overrides) -> AnswerKey:
    data = {
        "case_id": "T1",
        "source": "HAR-07/02",
        "status": "draft",
        "events": [
            {
                "id": "E01",
                "date": "1999-10-07",
                "summary": "Contractor reports anchor movement",
                "evidence": [{"file_no": 1, "page": 1, "quote": "appear to show signs of tensile movement"}],
                "ntsb": NTSB,
                "split": "dev",
                "core": True,
            }
        ],
        "negatives": [],
        "parties": [
            {"id": "P01", "name": "A", "kind": "organization", "role": "contractor", "ntsb": NTSB},
            {"id": "P02", "name": "B", "kind": "organization", "role": "consultant", "ntsb": NTSB},
        ],
        "relationships": [
            {"id": "R01", "source": "P02", "type": "represented", "target": "P01", "evidence": [], "ntsb": NTSB, "split": "dev"}
        ],
    }
    data.update(overrides)
    return AnswerKey.model_validate(data)


def test_real_case_config_loads_and_withholds_investigation_files():
    config = CaseConfig.model_validate_json((DATA_DIR / "cases/HWY06MH024/case.json").read_text())
    assert len(config.readable()) == 36
    assert {f.file_no for f in config.withheld()} >= {24, 91, 92}  # the NTSB factual reports


def test_case_rejects_duplicate_file():
    with pytest.raises(ValidationError, match="more than once"):
        CaseConfig(
            case_id="T1", title="t", event_date="2006-07-10", event_summary="t",
            files=[FileAssignment(file_no=1, group=FileGroup.PROJECT_RECORD, reason="x")] * 2,
        )


def test_key_flags_evidence_from_withheld_file():
    assert key().check_against(case(FileGroup.PROJECT_RECORD)) == []
    problems = key().check_against(case(FileGroup.INVESTIGATION))
    assert problems == ["E01 cites file 1, which the agent cannot read"]


def test_key_rejects_relationship_to_unknown_party():
    rel = {"id": "R01", "source": "P09", "type": "represented", "target": "P01", "evidence": [], "ntsb": NTSB, "split": "dev"}
    with pytest.raises(ValidationError, match="not in the key"):
        key(relationships=[rel])


def test_key_rejects_wrong_prefix_and_bad_date():
    with pytest.raises(ValidationError):
        key(parties=[{"id": "E05", "name": "A", "kind": "organization", "role": "x", "ntsb": NTSB}], relationships=[])
    with pytest.raises(ValidationError):
        key(events=[{**key().events[0].model_dump(), "date": "Oct 1999"}])
