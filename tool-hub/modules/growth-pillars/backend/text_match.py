import re

_STOP = {
    "the", "and", "for", "with", "of", "a", "an", "in", "on", "to", "inc", "ltd", "llc",
    "labs", "company", "co", "corp", "group", "engineering", "services", "solutions",
}


def tokens(text: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9.+-]*", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def overlap(a: str | list[str] | None, b: str | list[str] | None) -> float:
    """Share of a's tokens that also appear in b (0..1)."""
    ta = tokens(" ".join(a) if isinstance(a, list) else a)
    tb = tokens(" ".join(b) if isinstance(b, list) else b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta)


def normalize_domain(value: str | None) -> str:
    v = (value or "").lower().strip()
    v = re.sub(r"^https?://", "", v)
    v = v.removeprefix("www.")
    return v.split("/")[0]


def same_company(a: str | None, b: str | None) -> bool:
    na = re.sub(r"[^a-z0-9]", "", (a or "").lower())
    nb = re.sub(r"[^a-z0-9]", "", (b or "").lower())
    if len(na) < 3 or len(nb) < 3:
        return False
    return na == nb or na in nb or nb in na


def lead_domains(lead: dict) -> list[str]:
    names = [m.get("domain_name") for m in lead.get("matched_domains") or [] if isinstance(m, dict)]
    ctx = (lead.get("domain_context") or {}).get("domain_name")
    if ctx:
        names.insert(0, ctx)
    return [n for n in dict.fromkeys(names) if n]
