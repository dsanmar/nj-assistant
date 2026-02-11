import re

def toc_entry_count(text: str) -> int:
    t = text or ""
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]

    count = 0
    pat_sub = re.compile(r"\b\d{3}\.\d{2}\b.*?\.{2,}.*?\b\d{1,4}\b$")
    pat_sec = re.compile(r"\bSECTION\s+\d{3}\b.*?\.{2,}.*?\b\d{1,4}\b$")
    pat_div = re.compile(r"\bDIVISION\s+\d{3}\b.*?\.{2,}.*?\b\d{1,4}\b$")

    for ln in lines:
        if pat_sub.search(ln) or pat_sec.search(ln) or pat_div.search(ln):
            count += 1
    return count

def toc_penalty(text: str, strong: bool = False) -> float:
    """
    Returns multiplier in (0,1].
    strong=True for section-intent queries.
    """
    n = toc_entry_count(text)
    if n <= 0:
        return 1.0
    if strong:
        return 1.0 / (1.0 + 3.0 * n)
    return 1.0 / (1.0 + 0.5 * n)

def is_section_intent(query: str) -> bool:
    q = (query or "").strip().upper()
    return bool(re.search(r"\b\d{3}(?:\.\d{2}){0,2}\b", q) or "SECTION" in q)
