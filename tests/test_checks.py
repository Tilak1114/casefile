from casefile.harness.checks import check_output
from casefile.harness.models import (
    AliasClaim,
    ClaimKind,
    DateSource,
    EventClaim,
    PartyMention,
    QuoteRef,
    ReaderOutput,
    RelationshipClaim,
    RelationType,
    Role,
)
from casefile.verify.index import CaseIndex, DocumentMetadata, IndexedDocument, IndexedPage, MetadataField

P = "C:040:p002"
TEXT = (
    "The Modern Continental Construction Company, Inc.\nOctober 7, 1999\n"
    "Bechtel/Parsons Brinckerhoff (B/PB)\n"
    "On September 9, 1999 a worker noticed anchors pulling out. A small percentage of the adhesive "
    "anchors in the HOV ceiling mockup appear to show signs of tensile movement."
)


def index() -> CaseIndex:
    meta = DocumentMetadata(date=MetadataField(value="1999-10-07", span="October 7, 1999", page_id=P))
    return CaseIndex(
        case_id="C",
        pages={P: IndexedPage(id=P, file_no=40, page=2, text=TEXT, is_label=False, document_id="C:040:d02")},
        documents={"C:040:d02": IndexedDocument(id="C:040:d02", doc_type="letter", page_ids=[P], is_label=False, metadata=meta)},
    )


def q(text: str) -> QuoteRef:
    return QuoteRef(page_id=P, quote=text)


def run(output: ReaderOutput):
    return check_output(output, index(), run_id="r", case_id="C", role=Role.TECHNICAL, worker_id="w1")


def test_event_dated_by_document_uses_metadata():
    ok = run(ReaderOutput(events=[EventClaim(date="1999-10-07", date_source=DateSource.DOCUMENT_DATE,
                                             statement="MCC reports movement", quotes=[q("appear to show signs of tensile movement")])]))
    assert ok[0].verified
    wrong = run(ReaderOutput(events=[EventClaim(date="1999-10-08", date_source=DateSource.DOCUMENT_DATE,
                                                statement="MCC reports movement", quotes=[q("appear to show signs of tensile movement")])]))
    assert not wrong[0].verified and "date" in wrong[0].reasons[0]


def test_event_dated_in_text_needs_a_quote_showing_the_date():
    ok = run(ReaderOutput(events=[EventClaim(date="1999-09-09", date_source=DateSource.STATED_IN_TEXT,
                                             statement="A worker notices anchors pulling out",
                                             quotes=[q("On September 9, 1999 a worker noticed anchors pulling out")])]))
    assert ok[0].verified
    no_date = run(ReaderOutput(events=[EventClaim(date="1999-09-09", date_source=DateSource.STATED_IN_TEXT,
                                                  statement="A worker notices anchors pulling out",
                                                  quotes=[q("a worker noticed anchors pulling out")])]))
    assert not no_date[0].verified and "no quote shows the date" in no_date[0].reasons[0]


def test_party_name_must_be_in_its_quote():
    ok = run(ReaderOutput(parties=[PartyMention(name="Bechtel/Parsons Brinckerhoff", kind="organization", role="management consultant",
                                                quotes=[q("Bechtel/Parsons Brinckerhoff (B/PB)")])]))
    assert ok[0].verified and ok[0].kind is ClaimKind.PARTY
    bad = run(ReaderOutput(parties=[PartyMention(name="Gannett Fleming", kind="organization", role="designer",
                                                 quotes=[q("Bechtel/Parsons Brinckerhoff (B/PB)")])]))
    assert not bad[0].verified


def test_relationship_needs_both_parties_in_the_quotes():
    ok = run(ReaderOutput(relationships=[RelationshipClaim(
        source="The Modern Continental Construction Company, Inc.", type=RelationType.CONTRACTED_WITH,
        target="Bechtel/Parsons Brinckerhoff",
        quotes=[q("The Modern Continental Construction Company, Inc."), q("Bechtel/Parsons Brinckerhoff (B/PB)")])]))
    assert ok[0].verified
    bad = run(ReaderOutput(relationships=[RelationshipClaim(
        source="Powers Fasteners", type=RelationType.SUPPLIED, target="Bechtel/Parsons Brinckerhoff",
        quotes=[q("Bechtel/Parsons Brinckerhoff (B/PB)")])]))
    assert not bad[0].verified


def test_alias_quote_must_contain_both_names():
    ok = run(ReaderOutput(aliases=[AliasClaim(name="Bechtel/Parsons Brinckerhoff", same_as="B/PB", quote=q("Bechtel/Parsons Brinckerhoff (B/PB)"))]))
    assert ok[0].verified
    bad = run(ReaderOutput(aliases=[AliasClaim(name="Bechtel/Parsons Brinckerhoff", same_as="MCC", quote=q("Bechtel/Parsons Brinckerhoff (B/PB)"))]))
    assert not bad[0].verified


def test_claim_ids_are_stable_for_the_same_content():
    out = ReaderOutput(parties=[PartyMention(name="B/PB", kind="organization", role="consultant", quotes=[q("Bechtel/Parsons Brinckerhoff (B/PB)")])])
    assert run(out)[0].id == run(out)[0].id


def test_party_names_merge_only_on_formatting():
    from casefile.harness.assemble import name_key

    assert name_key("Modern Continental Construction Company, Inc.") == name_key("MODERN CONTINENTAL CONSTRUCTION CO.")
    assert name_key("Bechtel/Parsons Brinckerhoff") == name_key("BECHTEL / PARSONS BRINCKERHOFF")
    assert name_key("B/PB") != name_key("Bechtel/Parsons Brinckerhoff")  # needs a quoted alias


def test_a_name_written_with_different_formatting_is_in_its_quote():
    ok = run(ReaderOutput(parties=[PartyMention(name="MODERN CONTINENTAL CONSTRUCTION CO.", kind="organization", role="contractor",
                                                quotes=[q("The Modern Continental Construction Company, Inc.")])]))
    assert ok[0].verified
    partial = run(ReaderOutput(parties=[PartyMention(name="Continental Construction Group", kind="organization", role="contractor",
                                                     quotes=[q("The Modern Continental Construction Company, Inc.")])]))
    assert not partial[0].verified  # words must all appear, in order, as whole words


def rel_bpb_to_mcc(quote: str):
    return run(ReaderOutput(relationships=[RelationshipClaim(
        source="Bechtel/Parsons Brinckerhoff", type=RelationType.OVERSAW, target="The Modern Continental Construction Company, Inc.",
        quotes=[q(quote)])]))[0]


def alias(name: str, same_as: str, quote: str):
    return run(ReaderOutput(aliases=[AliasClaim(name=name, same_as=same_as, quote=q(quote))]))[0]


def test_a_refused_name_is_reinstated_through_a_verified_alias():
    from casefile.harness.checks import reinstate_by_alias

    TEXT_BPB = "B/PB directed The Modern Continental Construction Company, Inc. to retest"
    global TEXT
    old, TEXT = TEXT, TEXT + "\n" + TEXT_BPB
    try:
        refused = rel_bpb_to_mcc(TEXT_BPB)
        assert not refused.verified and refused.reasons == ["'Bechtel/Parsons Brinckerhoff' does not appear in the quotes"]
        known = alias("Bechtel/Parsons Brinckerhoff", "B/PB", "Bechtel/Parsons Brinckerhoff (B/PB)")
        [back] = reinstate_by_alias([refused], [known])
        assert back.verified and back.reasons == [] and back.name_aliases == {"Bechtel/Parsons Brinckerhoff": known.id}
        assert reinstate_by_alias([refused], []) == []  # no alias, stays refused
    finally:
        TEXT = old


def test_only_name_refusals_are_reinstated():
    from casefile.harness.checks import reinstate_by_alias

    other = rel_bpb_to_mcc("B/PB wrote this sentence that is not on the page")
    assert any(r.startswith("quote not found") for r in other.reasons)
    known = alias("Bechtel/Parsons Brinckerhoff", "B/PB", "Bechtel/Parsons Brinckerhoff (B/PB)")
    assert reinstate_by_alias([other], [known]) == []
