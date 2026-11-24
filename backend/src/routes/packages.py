"""Package grouping preview and append-only actual-minute corrections."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.packages import build_groups, observations
from src.models.identity import User
from src.models.source import Dataset
from src.schemas.requests import CorrectionRequest
from src.services.audit import record
from src.services.corrections import add_correction, correction_payload, list_corrections
from src.utils.time import iso

router = APIRouter(prefix='/datasets')


def _require_dataset(db, dataset_id):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, '找不到指定的数据批次')
    return dataset


def _package_view(dataset, corrections):
    grouped = build_groups(dataset.rows, [
        {"id": item.id, "package_id": item.package_id, "actual_minutes": item.actual_minutes,
         "reason": item.reason, "author": item.author, "created_at": item.created_at.isoformat()}
        for item in corrections
    ])
    records = observations(dataset.rows, grouped["groups"])
    groups = []
    for item in records:
        groups.append({
            "key": item["key"],
            "package_ids": list(item["package_ids"]),
            "job_ids": list(item["job_ids"]),
            "job_date": item["job_date"],
            "last_date": item["last_date"],
            "titles": list(item["titles"]),
            "actual_minutes": item["actual_minutes"],
            "has_conflict": item["has_conflict"],
            "source": ("correction" if item["correction"] else "conflict" if item["has_conflict"] else "csv"),
            "correction": item["correction"],
        })
    return {"groups": groups, "conflict_notes": grouped["conflict_notes"],
            "known_package_ids": sorted({pid for item in groups for pid in item["package_ids"]})}


@router.get('/{dataset_id}/packages')
def packages(dataset_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    dataset = _require_dataset(db, dataset_id)
    corrections = list_corrections(db, dataset_id)
    return {**_package_view(dataset, corrections), "corrections": correction_payload(corrections)}


@router.post('/{dataset_id}/corrections', status_code=201)
def correct(dataset_id: int, body: CorrectionRequest, db: Session = Depends(connection),
            actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    dataset = _require_dataset(db, dataset_id)
    package_ids = {row.get("package_id") for row in dataset.rows if row.get("package_id")}
    if body.package_id not in package_ids:
        raise HTTPException(404, '该批次中找不到这个整包包号，请先核对导入的 CSV')
    # Append-only insert: a concurrent request commits its own row, both stay.
    item = add_correction(db, dataset_id, body.package_id, body.actual_minutes, body.reason, actor.username)
    record(db, actor.username, 'correction.added', item.id,
           dataset_id=dataset_id, package_id=body.package_id, actual_minutes=body.actual_minutes)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "package_id": item.package_id, "actual_minutes": item.actual_minutes,
            "reason": item.reason, "author": item.author, "created_at": iso(item.created_at)}
