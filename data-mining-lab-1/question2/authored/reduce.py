"""
Turns a raw notice (title + body, as scraped) into candidate text
representations, each of which will be scored under Jaccard-over-shingles.

Evidence for what counts as signal vs. noise lives in
question2/README.md's "Evidence for the signal/noise split" section,
pulled from real corpus samples -- this module only encodes the decision.
"""
import re

NODAL_PREAMBLE_MARKERS = [
    "NATIONAL PROCUREMENT AGGREGATION SERVICE",
    "STATE PROCUREMENT CELL",
]

# Section headers that start a block we treat as noise once we are past
# the stable "identity" fields (name of work / procuring entity / scope).
NOISE_SECTION_HEADERS = re.compile(
    r"^(ABSTRACT BILL OF QUANTITIES|KEY DATES|CONTACT|GENERAL CONDITIONS)\s*$",
    re.MULTILINE,
)

DISCLAIMER_RE = re.compile(
    r"Disclaimer:.*$", re.DOTALL | re.IGNORECASE
)

REF_NUMBER_RE = re.compile(r"Tender reference number:.*?(?:\.|$)", re.IGNORECASE)

MONEY_RE = re.compile(
    r"(Rs\.?|INR|RUPEES)\s*[\d,\.]+\s*(lakh|cr|crore|only)?|\b\d{5,}\b",
    re.IGNORECASE,
)

WHITESPACE_RE = re.compile(r"\s+")


def strip_preamble(body: str) -> str:
    """Drop the nodal-aggregator boilerplate block that precedes the actual
    notice. The block ends at a '===' or '---' divider, or at the first
    'Name of work:' line, whichever comes first."""
    for marker in NODAL_PREAMBLE_MARKERS:
        if marker in body:
            idx = body.find("Name of work:")
            if idx != -1:
                return body[idx:]
    return body


def extract_identity_block(body: str) -> str:
    """Keep only the part of the notice whose wording is generated once per
    *opportunity* and repeated verbatim on every copy: the work name, the
    procuring entity, and the scope-of-work narrative. Drop reference
    numbers, money formatting, the bill-of-quantities table, key dates,
    contact details and the general-conditions footer -- all of which
    demonstrably vary copy-to-copy for the same opportunity (see
    evidence.md)."""
    body = strip_preamble(body)
    body = DISCLAIMER_RE.sub("", body)

    cut = NOISE_SECTION_HEADERS.search(body)
    if cut:
        body = body[: cut.start()]

    body = REF_NUMBER_RE.sub("", body)
    return body


def normalize(text: str) -> str:
    text = text.lower()
    text = MONEY_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def word_shingles(text: str, k: int) -> set:
    words = text.split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def char_shingles(text: str, k: int) -> set:
    text = text.replace(" ", "")
    if len(text) < k:
        return {text} if text else set()
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def represent(notice: dict, mode: str) -> set:
    """mode in {"raw_word5", "signal_word5", "signal_char8"}"""
    title, body = notice["title"], notice["body"]
    full_raw = title + " " + body

    if mode == "raw_word5":
        return word_shingles(normalize(full_raw), 5)

    identity = title + " " + extract_identity_block(body)
    norm = normalize(identity)

    if mode == "signal_word5":
        return word_shingles(norm, 5)
    if mode == "signal_char8":
        return char_shingles(norm, 8)

    raise ValueError(mode)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a) + len(b) - inter
    return inter / union
