import pytest

from casefile.ingest.metadata import ProposedField, ProposedMetadata, check, date_matches_span

PAGE = "MODERN CONTINENTAL CONSTRUCTION CO., INC.\nOctober 7, 1999\nBechtel/Parsons Brinckerhoff\nRe: HOV ceiling"


@pytest.mark.parametrize(
    "value,span,ok",
    [
        ("1999-10-07", "October 7, 1999", True),
        ("1999-10-07", "10/7/99", True),
        ("1999-10-13", "10.13.99", True),
        ("1999-10", "Oct. 1999", True),
        ("1999", "December 1998", False),
        ("1999-11-07", "October 7, 1999", False),
        ("Oct 7 1999", "October 7, 1999", False),
    ],
)
def test_date_must_be_shown_by_its_span(value, span, ok):
    assert date_matches_span(value, span) is ok


def field(value, span, page="p2"):
    return ProposedField(value=value, span=span, page_id=page)


def test_check_keeps_fields_whose_span_is_on_the_page():
    meta, dropped = check(
        ProposedMetadata(
            date=field("1999-10-07", "October 7, 1999"),
            author_org=field("MODERN CONTINENTAL CONSTRUCTION CO., INC.", "MODERN CONTINENTAL CONSTRUCTION CO., INC."),
            recipient_org=field("Bechtel/Parsons Brinckerhoff", "Bechtel/Parsons Brinckerhoff"),
        ),
        {"p2": PAGE},
    )
    assert dropped == []
    assert meta.date.value == "1999-10-07"


def test_check_drops_invented_span_and_value_not_in_span():
    meta, dropped = check(
        ProposedMetadata(
            date=field("1999-10-07", "7 October 1999"),  # not how the page writes it
            author_org=field("Modern Continental Construction Company", "MODERN CONTINENTAL CONSTRUCTION CO., INC."),
            recipient_org=field("Bechtel/Parsons Brinckerhoff", "Bechtel/Parsons Brinckerhoff", page="p9"),
        ),
        {"p2": PAGE},
    )
    assert meta.date is None and meta.author_org is None and meta.recipient_org is None
    assert len(dropped) == 3
