"""监考自动排班、锁定与手工调整 API。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_utils import require_admin
from dependencies import get_db
from invigilation_engine import solve_batch
from invigilation_models import (
    InvigilationAssignment,
    InvigilationDutyRequirement,
    InvigilationDutyRole,
    InvigilationExamSession,
    InvigilationLocation,
    InvigilationTeacherProfile,
)

router = APIRouter(prefix="/api/invigilation", tags=["invigilation-solver"])


class SolveInput(BaseModel):
    persist: bool = True
    replace_unlocked: bool = True


class LockInput(BaseModel):
    locked: bool = True


class ManualAssignmentInput(BaseModel):
    session_id: int
    location_id: int
    duty_role_id: int
    teacher_profile_id: int
    locked: bool = True
    notes: Optional[str] = None


def _assignment_dict(row, db: Session):
    teacher = db.get(InvigilationTeacherProfile, row.teacher_profile_id)
    role = db.get(InvigilationDutyRole, row.duty_role_id)
    location = db.get(InvigilationLocation, row.location_id)
    session = db.get(InvigilationExamSession, row.session_id)
    return {
        "id": row.id,
        "session_id": row.session_id,
        "date": session.date.isoformat() if session else None,
        "slot_code": session.slot_code if session else None,
        "slot_name": session.slot_name if session else None,
        "location_id": row.location_id,
        "location_name": location.name if location else None,
        "duty_role_id": row.duty_role_id,
        "role_code": role.code if role else None,
        "role_name": role.name if role else None,
        "teacher_profile_id": row.teacher_profile_id,
        "teacher_name": teacher.professor_name if teacher else None,
        "source": row.source,
        "locked": row.locked,
        "notes": row.notes,
    }


@router.post("/solve/{batch_id}")
def run_solver(batch_id: int, payload: SolveInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    return solve_batch(
        db,
        batch_id,
        persist=payload.persist,
        replace_unlocked=payload.replace_unlocked,
    )


@router.get("/assignments")
def list_assignments(batch_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(InvigilationAssignment)
    if batch_id is not None:
        query = query.join(
            InvigilationExamSession,
            InvigilationAssignment.session_id == InvigilationExamSession.id,
        ).filter(InvigilationExamSession.batch_id == batch_id)
    rows = query.order_by(
        InvigilationAssignment.session_id,
        InvigilationAssignment.location_id,
        InvigilationAssignment.duty_role_id,
    ).all()
    return [_assignment_dict(row, db) for row in rows]


@router.post("/assignments/manual")
def create_manual_assignment(
    payload: ManualAssignmentInput,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    session = db.get(InvigilationExamSession, payload.session_id)
    teacher = db.get(InvigilationTeacherProfile, payload.teacher_profile_id)
    role = db.get(InvigilationDutyRole, payload.duty_role_id)
    location = db.get(InvigilationLocation, payload.location_id)
    if not session or not teacher or not role or not location:
        raise HTTPException(status_code=400, detail="考试时段、人员、岗位或地点不存在")

    requirement = db.query(InvigilationDutyRequirement).filter(
        InvigilationDutyRequirement.session_id == payload.session_id,
        InvigilationDutyRequirement.location_id == payload.location_id,
        InvigilationDutyRequirement.duty_role_id == payload.duty_role_id,
    ).first()
    if not requirement:
        raise HTTPException(status_code=400, detail="该时段/地点没有这个岗位需求")

    conflict = db.query(InvigilationAssignment).filter(
        InvigilationAssignment.session_id == payload.session_id,
        InvigilationAssignment.teacher_profile_id == payload.teacher_profile_id,
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="该人员在此时段已经有监考任务")

    assigned_count = db.query(InvigilationAssignment).filter(
        InvigilationAssignment.session_id == payload.session_id,
        InvigilationAssignment.location_id == payload.location_id,
        InvigilationAssignment.duty_role_id == payload.duty_role_id,
    ).count()
    if assigned_count >= requirement.required_count:
        raise HTTPException(status_code=409, detail="该岗位已经满员，请先移除或替换现有人员")

    row = InvigilationAssignment(
        session_id=payload.session_id,
        location_id=payload.location_id,
        duty_role_id=payload.duty_role_id,
        teacher_profile_id=payload.teacher_profile_id,
        source="MANUAL",
        locked=payload.locked,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _assignment_dict(row, db)


@router.put("/assignments/{assignment_id}/lock")
def set_assignment_lock(
    assignment_id: int,
    payload: LockInput,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    row = db.get(InvigilationAssignment, assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="监考分配不存在")
    row.locked = payload.locked
    db.commit()
    db.refresh(row)
    return _assignment_dict(row, db)


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationAssignment, assignment_id)
    if not row:
        raise HTTPException(status_code=404, detail="监考分配不存在")
    db.delete(row)
    db.commit()
    return {"success": True}
