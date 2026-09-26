"""What the verifier checks against: the case's readable pages, documents and their metadata."""

from pydantic import BaseModel, ConfigDict, Field

from casefile.verify.models import PartialDate


class IndexedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    file_no: int
    page: int
    text: str
    is_label: bool
    document_id: str | None = None


class MetadataField(BaseModel):
    """A metadata value and the exact span of document text it was read from."""

    model_config = ConfigDict(frozen=True)

    value: str
    span: str = Field(min_length=1)
    page_id: str


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: MetadataField | None = None
    author_org: MetadataField | None = None
    recipient_org: MetadataField | None = None


class IndexedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    doc_type: str
    page_ids: list[str]
    is_label: bool
    metadata: DocumentMetadata = DocumentMetadata()

    @property
    def date(self) -> PartialDate | None:
        return self.metadata.date.value if self.metadata.date else None


class CaseIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    pages: dict[str, IndexedPage]
    documents: dict[str, IndexedDocument]

    def document_of(self, page_id: str) -> IndexedDocument | None:
        page = self.pages.get(page_id)
        return self.documents.get(page.document_id) if page and page.document_id else None
