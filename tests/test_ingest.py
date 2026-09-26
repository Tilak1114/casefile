import json
from pathlib import Path

from casefile.ingest.clean import clean_block, page_text
from casefile.ingest.models import ReductoBlock
from casefile.ingest.pipeline import documents_from_split, ingest_file

FIXTURES = Path(__file__).parent / "fixtures"


def block(content: str, type_: str = "Text", page: int = 1) -> ReductoBlock:
    return ReductoBlock(
        type=type_, content=content, bbox={"left": 0, "top": 0, "width": 1, "height": 0.1, "page": page}
    )


def test_clean_strips_markup_but_keeps_page_characters():
    text, removed = clean_block("Mr. <b>LYNN</b> said “submitt” 3,200 pounds<sup>1</sup> [Redacted] Gannett &amp; Fleming")
    assert text == "Mr. LYNN said “submitt” 3,200 pounds1 Gannett & Fleming"
    assert removed["<b>"] == 2 and removed["<sup>"] == 2
    assert removed["[Redacted]"] == 1 and removed["entity"] == 1


def test_clean_flattens_tables_to_rows():
    text, removed = clean_block("<table><tr><td>Slope</td><td>2.0%</td></tr><tr><td>CO 4</td><td>0.75%</td></tr></table>")
    assert text.split("\n") == ["Slope 2.0%", "CO 4 0.75%"]
    assert removed["table_row"] == 2


def test_page_text_drops_figures_and_records_block_spans():
    text, spans, _, figures = page_text(
        [block("Logo of the project", "Figure"), block("First line"), block("<b>Second</b> line")]
    )
    assert text == "First line\nSecond line"
    assert figures == 1
    assert [text[s.start : s.end] for s in spans] == ["First line", "Second line"]


def test_split_partitions_become_documents_in_page_order():
    split = json.loads((FIXTURES / "split_bundle.json").read_text())
    docs = documents_from_split("T1", 93, split)
    assert [d.index for d in docs] == list(range(1, len(docs) + 1))
    firsts = [d.pages[0] for d in docs]
    assert firsts == sorted(firsts)
    labels = [d for d in docs if d.is_label]
    assert len(labels) == 15  # the divider pages in the recorded bundle
    assert all(len(d.pages) == 1 for d in labels)


class FakeReducto:
    def parse(self, path, sha256):
        blocks = [
            {"type": "Title", "content": "ATTACHMENT 9", "bbox": {"left": 0, "top": 0, "width": 1, "height": 0.1, "page": 1}},
            {"type": "Figure", "content": "A logo", "bbox": {"left": 0, "top": 0, "width": 0.1, "height": 0.1, "page": 2}},
            {"type": "Text", "content": "appear to show signs of tensile movement", "bbox": {"left": 0, "top": 0.2, "width": 1, "height": 0.1, "page": 2}},
        ]
        return {"job_id": "j1", "usage": {"num_pages": 3, "credits": 2.4}, "result": {"chunks": [{"blocks": blocks}]}}, False

    def split(self, path, sha256, job_id, request):
        splits = [
            {"name": "production_label", "pages": [1], "conf": "high", "partitions": None},
            {"name": "letter", "pages": [2], "conf": "high", "partitions": [{"name": "C09B2-114", "pages": [2], "conf": "high"}]},
        ]
        return {"usage": {"credits": 4.0}, "result": {"splits": splits}}, False


def test_ingest_file_marks_labels_and_unassigned_pages():
    pages, docs, summary = ingest_file(FakeReducto(), "T1", 40, Path("x.pdf"), "0" * 64)
    assert [p.is_label for p in pages] == [True, False, False]
    assert pages[1].text == "appear to show signs of tensile movement"
    assert pages[1].figures_dropped == 1
    assert [d.doc_type for d in docs] == ["production_label", "letter"]
    assert summary.unassigned_pages == [3]
    assert summary.parse_credits == 2.4 and summary.split_credits == 4.0


def test_reducto_cache_miss_refuses_to_spend_by_default(tmp_path):
    import pytest

    from casefile.ingest.reducto import ReductoClient, SpendNotAllowed

    def fail(_):
        raise AssertionError("no network call may be made")

    import httpx

    client = ReductoClient("key", tmp_path, http=httpx.Client(transport=httpx.MockTransport(fail)))
    with pytest.raises(SpendNotAllowed, match="--allow-spend"):
        client.parse(tmp_path / "x.pdf", "0" * 64)


def test_reducto_cache_is_read_back_without_private_links(tmp_path):
    from casefile.ingest.reducto import ReductoClient

    client = ReductoClient(None, tmp_path)
    path = client._cache_path("0" * 64, "parse", {"a": 1})
    client._write(path, {"job_id": "j", "pdf_url": "https://signed", "studio_link": "https://studio"})
    assert client._read(path) == {"job_id": "j"}
