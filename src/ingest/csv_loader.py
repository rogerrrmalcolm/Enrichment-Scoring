from __future__ import annotations

import csv
from pathlib import Path

from src.models.entities import ContactRecord


def load_contacts(csv_path: Path) -> list[ContactRecord]:
    contacts: list[ContactRecord] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            contacts.append(
                ContactRecord(
                    contact_name=row["Contact Name"].strip(),
                    organization=row["Organization"].strip(),
                    org_type=row["Org Type"].strip(),
                    role=row["Role"].strip(),
                    email=(row["Email"].strip() or None),
                    region=row["Region"].strip(),
                    contact_status=row["Contact Status"].strip(),
                    relationship_depth=int(row["Relationship Depth"].strip()),
                )
            )
    return contacts
