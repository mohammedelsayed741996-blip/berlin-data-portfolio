"""Tokenising, light stemming and an English-German synonym map for HR vocabulary.

Employees ask in their own words, often mixing German terms into English ("how many Urlaub days").
The synonym map expands a query with the words the policies actually use.
"""

from __future__ import annotations

import re

STOP = set("""a an and are as at be by can do does for from has have how i if in is it its me my of on or our
should so than that the their them then there these this to us was we what when where which who why will with
you your yours am get got any much many""".split())

SYNONYMS = {
    "urlaub": ["annual", "leave"], "vacation": ["annual", "leave"], "holiday": ["annual", "leave"], "holidays": ["annual", "leave"],
    "pto": ["annual", "leave"], "days off": ["leave"], "krank": ["sick", "illness"], "krankmeldung": ["sick", "certificate"],
    "sick note": ["medical", "certificate"], "doctor's note": ["medical", "certificate"], "au": ["certificate", "incapacity"],
    "elternzeit": ["parental", "leave"], "paternity": ["partner", "leave", "parental"], "maternity": ["parental", "leave"],
    "baby": ["birth", "child"], "überstunden": ["overtime"], "ueberstunden": ["overtime"], "extra hours": ["overtime"],
    "gleitzeit": ["flexitime"], "flextime": ["flexitime"], "core time": ["core", "hours"], "homeoffice": ["remote", "mobile"],
    "home office": ["remote", "mobile"], "wfh": ["remote", "mobile"], "work from home": ["remote", "mobile"],
    "dienstreise": ["business", "travel", "trip"], "per diem": ["meal", "allowance", "per", "diem"], "spesen": ["expenses"],
    "reisekosten": ["travel", "expenses"], "zuschlag": ["allowance"], "zuschläge": ["allowance"], "nachtschicht": ["night", "shift"],
    "weiterbildung": ["training", "learning"], "course": ["training", "courses"], "deutschkurs": ["german", "courses", "language"],
    "betriebsrat": ["works", "council"], "whistleblower": ["report", "reporting", "speak"], "hinweisgeber": ["report", "reporting"],
    "gehalt": ["salary", "pay"], "gehaltsband": ["salary", "bands"], "raise": ["merit", "increase"], "pay rise": ["merit", "increase"],
    "bonus": ["merit", "increase"], "datenschutz": ["data", "protection", "privacy"], "gdpr": ["data", "privacy", "rights"],
    "dsgvo": ["data", "privacy", "rights"], "kita": ["daycare", "childcare"], "jobticket": ["deutschlandticket", "ticket"],
    "e-bike": ["bike", "leasing"], "ebike": ["bike", "leasing"], "shuttle": ["shuttle", "buses"], "commute": ["commuting", "shuttle"],
    "wedding": ["wedding", "special", "leave"], "married": ["wedding", "special", "leave"], "moving": ["moving", "special", "leave"],
    "funeral": ["death", "special", "leave"], "abroad": ["another", "country"], "laptop": ["equipment", "laptop"],
    "receipts": ["receipts", "expense", "claim"], "rating": ["rating", "scale", "performance"], "pip": ["performance", "improvement", "plan"],
}


IRREGULAR = {"paid": "pay", "took": "take", "taken": "take", "gave": "give", "given": "give", "left": "leave", "kept": "keep",
             "told": "tell", "children": "child", "men": "man", "women": "woman", "flew": "fly", "flown": "fly"}


def stem(w: str) -> str:
    """Light suffix stripping so that approve, approves, approved and approval meet in one form."""
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) <= 4 or w.isdigit():
        return w
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ed", ""), ("al", ""), ("es", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + rep
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zäöüß0-9]+", text.lower())
    return [stem(w) for w in words if w not in STOP]


# question patterns that point to a kind of section rather than a topic word
INTENTS = [
    # "how many vacation days / how much Urlaub": the entitlement section, unless a specific kind of leave is named
    (re.compile(r"^(?!.*\b(special|wedding|moving|birth|baby|death|dies|sick|ill|parental|elternzeit|week|home|remote)\b)"
                r"(?=.*\bhow (many|much)\b)(?=.*\b(vacation|holidays?|urlaub|annual leave|leave days|days off|pto)\b)"),
     ["entitlement", "receive", "working", "days"]),
]


def expand(query: str) -> str:
    """Add the policies' own words for any synonym or question pattern found in the query."""
    q = query.lower()
    extra = []
    for rx, words in INTENTS:
        if rx.search(q):
            extra.extend(words)
    for k, v in SYNONYMS.items():
        if re.search(rf"(?<![a-zäöüß]){re.escape(k)}(?![a-zäöüß])", q):
            extra.extend(v)
    return query + (" " + " ".join(extra) if extra else "")
