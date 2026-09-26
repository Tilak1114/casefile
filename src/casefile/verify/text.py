"""Exact quote matching.

Comparison collapses runs of whitespace and folds curly quotes and dashes to their plain forms. Nothing
else is forgiven: case, spelling, punctuation and word order must match. Stored text is never changed;
matches are reported as offsets into the original text.
"""

FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ",
})


def _normalise(text: str) -> tuple[str, list[int]]:
    """Normalised text and, for each of its characters, the index of the original character."""
    out: list[str] = []
    origin: list[int] = []
    in_space = False
    for i, ch in enumerate(text.translate(FOLD)):
        if ch.isspace():
            if not in_space and out:
                out.append(" ")
                origin.append(i)
            in_space = True
            continue
        in_space = False
        out.append(ch)
        origin.append(i)
    if out and out[-1] == " ":
        out.pop()
        origin.pop()
    return "".join(out), origin


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """(start, end) offsets of the quote in the original text, or None."""
    haystack, origin = _normalise(text)
    needle, _ = _normalise(quote)
    if not needle:
        return None
    at = haystack.find(needle)
    if at < 0:
        return None
    return origin[at], origin[at + len(needle) - 1] + 1
