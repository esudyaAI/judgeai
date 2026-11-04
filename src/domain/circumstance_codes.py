"""Parse an explicitly cited circumstance norm; never infer it from case prose."""

import re


def circumstance_codes(norm: str) -> set[str]:
    match = re.search(r"ч\.?\s*(\d(?:\.\d)?)\s*ст\.?\s*(61|63)(?!\d)", norm, re.I)
    if not match:
        return set()
    points = re.findall(r'[«"“]([а-яё])[»"”]', norm[: match.start()], re.I)
    base = f"{match[2]}.{match[1]}"
    return {f"{base}.{p.lower()}" for p in points} if points else {base}
