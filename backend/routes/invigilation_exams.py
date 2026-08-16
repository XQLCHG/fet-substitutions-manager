"""考试批次、时段、考场与监考岗位需求 API。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_utils import require_admin
from dependencies import get_db
from invigilation_defaults import seed_defaults
from invigilation_models import (
    InvigilationDutyRequirement,
    InvigilationDutyRole,
    InvigilationExamBatch,
    InvigilationExamRoom,
    InvigilationExamSession,
    InvigilationLocation,
)

router = APIRouter(prefix="/api/invigilation", tags=["invigilation-exams"])


class BatchInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    academic_year: Optional[str] = None
    term: Optional[str] = None
    status: str = "DRAFT"
    notes: Optional[str] = None


class SessionInput(BaseModel):
    batch_id: int
    date: date
    slot_code: str = Field(min_length=1, max_length=50)
    slot_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    sort_order: int = 0
    notes: Optional[str] = None


class ExamRoomInput(BaseModel):
    session_id: int
    room_location_id: int
    course_code: Optional[str] = None
    course_name: str = Field(min_length=1, max_length=300)
    group_names: Optional[str] = None
    candidate_count: Optional[int] = Field(default=None, ge=0)
    department: Optional[str] = None
    course_teacher_names: Optional[str] = None
    notes: Optional[str] = None


class RequirementInput(BaseModel):
    session_id: int
    location_id: int
    duty_role_id: int
    required_count: int = Field(ge=0)
    notes: Optional[str] = None


def _batch_dict(row):
    return {
        "id": row.id,
        "name": row.name,
        "academic_year": row.academic_year,
        "term": row.term,
        "status": row.status,
        "notes": row.notes,
    }


def _session_dict(row):
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "date": row.date.isoformat(),
        "slot_code": row.slot_code,
        "slot_name": row.slot_name,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "sort_order": row.sort_order,
        "notes": row.notes,
    }


def _exam_room_dict(row):
    return {
        "id": row.id,
        "session_id": row.session_id,
        "room_location_id": row.room_location_id,
        "course_code": row.course_code,
        "course_name": row.course_name,
        "group_names": row.group_names,
        "candidate_count": row.candidate_count,
        "department": row.department,
        "course_teacher_names": row.course_teacher_names,
        "notes": row.notes,
    }


def _requirement_dict(row):
    return {
        "id": row.id,
        "session_id": row.session_id,
        "location_id": row.location_id,
        "duty_role_id": row.duty_role_id,
        "required_count": row.required_count,
        "notes": row.notes,
    }


@router.get("/batches")
def list_batches(db: Session = Depends(get_db)):
    rows = db.query(InvigilationExamBatch).order_by(InvigilationExamBatch.id.desc()).all()
    return [_batch_dict(r) for r in rows]


@router.post("/batches")
def create_batch(payload: BatchInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = InvigilationExamBatch(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _batch_dict(row)


@router.put("/batches/{batch_id}")
def update_batch(batch_id: int, payload: BatchInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationExamBatch, batch_id)
    if not row:
        raise HTTPException(status_code=404, detail="考试批次不存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _batch_dict(row)


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationExamBatch, batch_id)
    if not row:
        raise HTTPException(status_code=404, detail="考试批次不存在")
    db.delete(row)
    db.commit()
    return {"success": True}


@router.get("/sessions")
def list_sessions(batch_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(InvigilationExamSession)
    if batch_id is not None:
        query = query.filter(InvigilationExamSession.batch_id == batch_id)
    rows = query.order_by(InvigilationExamSession.date, InvigilationExamSession.sort_order,
                          InvigilationExamSession.slot_code).all()
    return [_session_dict(r) for r in rows]


@router.post("/sessions")
def create_session(payload: SessionInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not db.get(InvigilationExamBatch, payload.batch_id):
        raise HTTPException(status_code=400, detail="考试批次不存在")
    duplicate = db.query(InvigilationExamSession).filter(
        InvigilationExamSession.batch_id == payload.batch_id,
        InvigilationExamSession.date == payload.date,
        InvigilationExamSession.slot_code == payload.slot_code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="该批次的日期/时段已存在")
    row = InvigilationExamSession(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _session_dict(row)


@router.get("/exam-rooms")
def list_exam_rooms(session_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(InvigilationExamRoom)
    if session_id is not None:
        query = query.filter(InvigilationExamRoom.session_id == session_id)
    rows = query.order_by(InvigilationExamRoom.session_id, InvigilationExamRoom.room_location_id).all()
    return [_exam_room_dict(r) for r in rows]


@router.post("/exam-rooms")
def create_exam_room(payload: ExamRoomInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not db.get(InvigilationExamSession, payload.session_id):
        raise HTTPException(status_code=400, detail="考试时段不存在")
    location = db.get(InvigilationLocation, payload.room_location_id)
    if not location or location.location_type != "ROOM":
        raise HTTPException(status_code=400, detail="考场地点不存在或不是 ROOM 类型")
    duplicate = db.query(InvigilationExamRoom).filter(
        InvigilationExamRoom.session_id == payload.session_id,
        InvigilationExamRoom.room_location_id == payload.room_location_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="该时段的考场已经安排考试")
    row = InvigilationExamRoom(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _exam_room_dict(row)


@router.get("/requirements")
def list_requirements(session_id: Optional[int] = None, db: Session = Depends(get_db)):
    seed_defaults(db)
    query = db.query(InvigilationDutyRequirement)
    if session_id is not None:
        query = query.filter(InvigilationDutyRequirement.session_id == session_id)
    rows = query.order_by(InvigilationDutyRequirement.session_id,
                          InvigilationDutyRequirement.location_id,
                          InvigilationDutyRequirement.duty_role_id).all()
    return [_requirement_dict(r) for r in rows]


@router.post("/requirements")
def upsert_requirement(payload: RequirementInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    seed_defaults(db)
    if not db.get(InvigilationExamSession, payload.session_id):
        raise HTTPException(status_code=400, detail="考试时段不存在")
    location = db.get(InvigilationLocation, payload.location_id)
    role = db.get(InvigilationDutyRole, payload.duty_role_id)
    if not location or not role:
        raise HTTPException(status_code=400, detail="地点或岗位不存在")
    if location.location_type != role.scope_type:
        raise HTTPException(
            status_code=400,
            detail=f"岗位 {role.name} 作用范围为 {role.scope_type}，不能配置在 {location.location_type} 地点",
        )
    row = db.query(InvigilationDutyRequirement).filter(
        InvigilationDutyRequirement.session_id == payload.session_id,
        InvigilationDutyRequirement.location_id == payload.location_id,
        InvigilationDutyRequirement.duty_role_id == payload.duty_role_id,
    ).first()
    if row:
        row.required_count = payload.required_count
        row.notes = payload.notes
    else:
        row = InvigilationDutyRequirement(**payload.model_dump())
        db.add(row)
    db.commit()
    db.refresh(row)
    return _requirement_dict(row)


@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationDutyRequirement, requirement_id)
    if not row:
        raise HTTPException(status_code=404, detail="岗位需求不存在")
    db.delete(row)
    db.commit()
    return {"success": True}


@router.get("/overview/{batch_id}")
def batch_overview(batch_id: int, db: Session = Depends(get_db)):
    """供前端和求解器使用的批次汇总。"""
    batch = db.get(InvigilationExamBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="考试批次不存在")

    sessions = db.query(InvigilationExamSession).filter(
        InvigilationExamSession.batch_id == batch_id
    ).order_by(InvigilationExamSession.date, InvigilationExamSession.sort_order).all()
    session_ids = [s.id for s in sessions]

    exam_rooms = []
    requirements = []
    if session_ids:
        exam_rooms = db.query(InvigilationExamRoom).filter(
            InvigilationExamRoom.session_id.in_(session_ids)
        ).all()
        requirements = db.query(InvigilationDutyRequirement).filter(
            InvigilationDutyRequirement.session_id.in_(session_ids)
        ).all()

    total_required = sum(r.required_count for r in requirements)
    return {
        "batch": _batch_dict(batch),
        "sessions": [_session_dict(s) for s in sessions],
        "exam_rooms": [_exam_room_dict(r) for r in exam_rooms],
        "requirements": [_requirement_dict(r) for r in requirements],
        "summary": {
            "session_count": len(sessions),
            "exam_room_count": len(exam_rooms),
            "duty_positions": total_required,
        },
    }
