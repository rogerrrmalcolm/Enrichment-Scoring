from __future__ import annotations

import csv
from pathlib import Path

from src.models.entities import ContactRecord


def load_contacts(csv_path: Path) -> list[ContactRecord]:
    contacts: list[ContactRecord] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cleaned_row = {key: (value or "").strip() for key, value in row.items()}
            if not any(cleaned_row.values()):
                continue
            if not _has_required_contact_fields(cleaned_row):
                continue
            relationship_depth = _parse_relationship_depth(cleaned_row["Relationship Depth"])
            if relationship_depth is None:
                continue
            contacts.append(
                ContactRecord(
                    contact_name=cleaned_row["Contact Name"],
                    organization=cleaned_row["Organization"],
                    org_type=cleaned_row["Org Type"],
                    role=cleaned_row["Role"],
                    email=(cleaned_row["Email"] or None),
                    region=cleaned_row["Region"],
                    contact_status=cleaned_row["Contact Status"],
                    relationship_depth=relationship_depth,
                )
            )
    return contacts


def _has_required_contact_fields(row: dict[str, str]) -> bool:
    required_fields = (
        "Contact Name",
        "Organization",
        "Org Type",
        "Region",
        "Contact Status",
        "Relationship Depth",
    )
    return all(row.get(field, "") for field in required_fields)


def _parse_relationship_depth(raw_value: str) -> int | None:
    try:
        relationship_depth = int(raw_value)
    except ValueError:
        return None
    if not 1 <= relationship_depth <= 10:
        return None
    return relationship_depth
