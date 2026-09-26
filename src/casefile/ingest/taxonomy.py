"""Document types for splitting construction project records into original documents."""

from pydantic import BaseModel, ConfigDict


class DocType(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str


PRODUCTION_LABEL = "production_label"

DOC_TYPES: list[DocType] = [
    DocType(name="letter", description="A letter on letterhead from one organisation or person to another"),
    DocType(name="memorandum", description="An internal or inter-office memorandum"),
    DocType(name="email", description="An e-mail message or printed e-mail thread"),
    DocType(name="fax_transmittal", description="A facsimile cover sheet or fax transmittal"),
    DocType(
        name="submittal_transmittal",
        description="A submittal or transmittal form sending shop drawings, product data or samples for "
        "review, including review stamps and dispositions",
    ),
    DocType(name="request_for_information", description="A request for information (RFI) and its response"),
    DocType(name="change_order", description="A change order, contract modification or change directive"),
    DocType(name="meeting_minutes", description="Minutes or notes of a meeting"),
    DocType(name="daily_report", description="A daily report, field log or inspector's diary entries"),
    DocType(name="inspection_or_test_report", description="An inspection, test or laboratory report"),
    DocType(name="deficiency_report", description="A deficiency or nonconformance report and its disposition"),
    DocType(name="specification", description="Specification sections, contract provisions or general conditions"),
    DocType(name="drawing", description="A drawing, sketch or detail"),
    DocType(name="product_literature", description="Manufacturer literature, datasheets or catalogue pages"),
    DocType(name="procedure", description="A procedure, method statement or work plan"),
    DocType(
        name=PRODUCTION_LABEL,
        description="A slip sheet, cover sheet, divider or index page added by whoever assembled or produced "
        "the documents, describing what follows rather than being part of the original record. A page whose "
        "only content is a title or description of the following pages (for example an exhibit or attachment "
        "number, a description of the document, a page count) is a production label even when only one "
        "document follows it.",
    ),
    DocType(name="other", description="Anything that fits none of the other types"),
]

PARTITION_KEY = "the individual document's own identity: its reference or letter number, or else its date and sender"

SPLIT_RULES = (
    "Each page belongs to exactly one section. A single file may contain many separate documents; "
    "keep each original document separate. Pages added when the documents were assembled (slip sheets, "
    "cover sheets, dividers) are never part of the document they introduce."
)


def split_description() -> list[dict]:
    return [{"name": t.name, "description": t.description, "partition_key": PARTITION_KEY} for t in DOC_TYPES]
