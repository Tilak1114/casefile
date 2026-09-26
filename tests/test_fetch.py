import hashlib

import httpx
import pytest
from pydantic import ValidationError

from casefile.docket.fetch import blob_url, fetch_docket
from casefile.docket.models import SourceEntry, SourceIndex

PDF = b"%PDF-1.4 test body"


def make_index(*names: str) -> SourceIndex:
    return SourceIndex(
        docket_id="TEST01",
        docket_url="https://data.ntsb.gov/Docket/?NTSBNumber=TEST01",
        files=[SourceEntry(file_no=i + 1, blob_id=str(100 + i), filename=n) for i, n in enumerate(names)],
    )


def test_blob_url_quotes_filename():
    entry = SourceEntry(file_no=1, blob_id="42", filename="Letter dated 7 Oct 1999.PDF")
    assert blob_url(entry).endswith("ID=42&FileExtension=.PDF&FileName=Letter%20dated%207%20Oct%201999.PDF")


def test_fetch_records_hash_and_size(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=PDF)))
    manifest = fetch_docket(make_index("a.PDF", "b.PDF"), tmp_path, client)
    assert [f.file_no for f in manifest.files] == [1, 2]
    assert manifest.files[0].sha256 == hashlib.sha256(PDF).hexdigest()
    assert manifest.files[0].bytes == len(PDF)
    assert (tmp_path / "fetch_manifest.json").exists()


def test_fetch_rejects_non_pdf(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>")))
    with pytest.raises(RuntimeError, match="1 of 1 files failed"):
        fetch_docket(make_index("a.PDF"), tmp_path, client)


def test_fetch_reuses_existing_file_without_network(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "001.pdf").write_bytes(PDF)

    def fail(_):
        raise AssertionError("network should not be used")

    manifest = fetch_docket(make_index("a.PDF"), tmp_path, httpx.Client(transport=httpx.MockTransport(fail)))
    assert manifest.files[0].bytes == len(PDF)


def test_source_entry_rejects_bad_blob_id():
    with pytest.raises(ValidationError):
        SourceEntry(file_no=1, blob_id="abc", filename="x.PDF")
