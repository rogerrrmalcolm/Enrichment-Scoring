from __future__ import annotations

import re
from collections import defaultdict

from src.models.entities import ContactRecord


def normalize_org_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def build_org_index(contacts: list[ContactRecord]) -> dict[str, list[ContactRecord]]:
    grouped: dict[str, list[ContactRecord]] = defaultdict(list)
    for contact in contacts:
        grouped[normalize_org_name(contact.organization)].append(contact)
    return dict(grouped)
