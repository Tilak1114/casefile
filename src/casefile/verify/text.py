"""Exact quote matching.

Comparison collapses runs of whitespace and folds curly quotes and dashes to their plain forms. A hyphen
that ends a line may also join the word across the break, keeping the hyphen (load-/displacement) or
dropping it (instal-/lation), because page text keeps the layout's line breaks. Nothing else is forgiven:
case, spelling, punctuation and word order must match. Stored text is never changed;
matches are reported as offsets into the original text.
"""

FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ",
})


def _normalise(text: str, join: str | None = None) -> tuple[str, list[int]]:
    """Normalised text and, for each of its characters, the index of the original character.

    `join` is None, "keep" or "drop": what to do with a hyphen followed by whitespace that holds a line break."""
    folded = text.translate(FOLD)
    out: list[str] = []
    origin: list[int] = []
    in_space = False
    i = 0
    while i < len(folded):
        ch = folded[i]
        if join and ch == "-":
            j = i + 1
            while j < len(folded) and folded[j].isspace():
                j += 1
            if "\n" in folded[i + 1:j] and j < len(folded):
                if join == "keep":
                    out.append("-")
                    origin.append(i)
                in_space = False
                i = j
                continue
        if ch.isspace():
            if not in_space and out:
                out.append(" ")
                origin.append(i)
            in_space = True
            i += 1
            continue
        in_space = False
        out.append(ch)
        origin.append(i)
        i += 1
    if out and out[-1] == " ":
        out.pop()
        origin.pop()
    return "".join(out), origin


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """(start, end) offsets of the quote in the original text, or None."""
    needle, _ = _normalise(quote)
    if not needle:
        return None
    for join in (None, "keep", "drop"):
        haystack, origin = _normalise(text, join)
        at = haystack.find(needle)
        if at >= 0:
            return origin[at], origin[at + len(needle) - 1] + 1
    return None
