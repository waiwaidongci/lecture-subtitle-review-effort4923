"""Data fingerprints and package-level actual-minute corrections.

A fingerprint covers the dataset rows and every append-only correction of the
batch. Re-importing changed rows or adding a correction changes the fingerprint,
so runs computed against the older inputs can be flagged as stale.
"""

import hashlib
import json


def _field(item, name):
    if isinstance(item, dict):
        return item[name]
    return getattr(item, name)


def correction_fingerprint(corrections):
    payload = []
    for item in corrections:
        created_at = _field(item, "created_at")
        payload.append({
            "id": _field(item, "id"),
            "package_id": _field(item, "package_id"),
            "actual_minutes": _field(item, "actual_minutes"),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        })
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def fingerprint(dataset_checksum, corrections):
    digest = hashlib.sha256()
    digest.update(dataset_checksum.encode())
    digest.update(b"|")
    digest.update(correction_fingerprint(corrections).encode())
    return digest.hexdigest()


def list_corrections(db, dataset_id):
    from sqlalchemy import select

    return list(db.scalars(
        select(PackageCorrection)
        .where(PackageCorrection.dataset_id == dataset_id)
        .order_by(PackageCorrection.package_id, PackageCorrection.id)
    ))


def correction_payload(items):
    return [
        {"id": item.id, "package_id": item.package_id, "actual_minutes": item.actual_minutes,
         "reason": item.reason, "author": item.author, "created_at": item.created_at.isoformat()}
        for item in items
    ]


def add_correction(db, dataset_id, package_id, actual_minutes, reason, actor):
    """Append a correction. No upsert: concurrent writes both survive."""
    from src.models.source import PackageCorrection

    item = PackageCorrection(dataset_id=dataset_id, package_id=package_id,
                             actual_minutes=actual_minutes, reason=reason, author=actor)
    db.add(item)
    db.flush()
    return item
