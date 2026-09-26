"""Build the verifier's index from what ingestion stored."""

from pymongo.database import Database

from casefile.ingest.models import page_id
from casefile.verify.index import CaseIndex, DocumentMetadata, IndexedDocument, IndexedPage


def load_index(db: Database, case_id: str) -> CaseIndex:
    documents: dict[str, IndexedDocument] = {}
    doc_of_page: dict[str, str] = {}
    metadata = {m["_id"]: m for m in db.metadata.find({"case_id": case_id})}
    for d in db.documents.find({"case_id": case_id}):
        pages = [page_id(case_id, d["file_no"], p) for p in d["pages"]]
        meta = metadata.get(d["_id"], {}).get("fields", {})
        documents[d["_id"]] = IndexedDocument(
            id=d["_id"], doc_type=d["doc_type"], page_ids=pages, is_label=d["is_label"],
            metadata=DocumentMetadata.model_validate(meta),
        )
        for p in pages:
            doc_of_page[p] = d["_id"]
    pages = {
        p["_id"]: IndexedPage(
            id=p["_id"], file_no=p["file_no"], page=p["page"], text=p["text"],
            is_label=p["is_label"], document_id=doc_of_page.get(p["_id"]),
        )
        for p in db.pages.find({"case_id": case_id})
    }
    return CaseIndex(case_id=case_id, pages=pages, documents=documents)
