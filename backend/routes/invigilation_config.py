"""中国高校监考扩展配置 API。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_utils import require_admin
from dependencies import get_db
from invigilation_defaults import seed_defaults
from invigilation_models import (
    LOCATION_TYPES,
    ROLE_SCOPE_TYPES,
    InvigilationDutyRole,
    InvigilationLocation,
    InvigilationRule,
    InvigilationTeacherProfile,
    InvigilationTeacherRoleQualification,
    InvigilationTeacherUnavailability,
)

router = APIRouter(prefix="/api/invigilation", tags=["invigilation"])


class RoleInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    scope_type: str
    workload_weight: float = Field(default=1.0, ge=0)
    default_required: int = Field(default=0, ge=0)
    sort_order: int = 0
    active: bool = True
    description: Optional[str] = None


class LocationInput(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    location_type: str
    parent_id: Optional[int] = None
    capacity: Optional[int] = Field(default=None, ge=0)
    sort_order: int = 0
    active: bool = True
    notes: Optional[str] = None


class TeacherProfileInput(BaseModel):
    professor_name: str = Field(min_length=1, max_length=200)
    employee_no: Optional[str] = None
    department: Optional[str] = None
    max_total_duties: Optional[int] = Field(default=None, ge=0)
    max_daily_duties: int = Field(default=2, ge=0)
    active: bool = True
    notes: Optional[str] = None


class QualificationInput(BaseModel):
    teacher_profile_id: int
    duty_role_id: int
    eligible: bool = True


class UnavailabilityInput(BaseModel):
    teacher_profile_id: int
    date: date
    slot_code: Optional[str] = None
    reason: Optional[str] = None


class RuleInput(BaseModel):
    value: str
    value_type: str = "string"
    description: Optional[str] = None


def _validate_role_scope(scope_type: str):
    if scope_type not in ROLE_SCOPE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效岗位作用范围: {scope_type}")


def _validate_location_type(location_type: str):
    if location_type not in LOCATION_TYPES:
        raise HTTPException(status_code=400, detail=f"无效地点类型: {location_type}")


def _role_dict(r):
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "scope_type": r.scope_type,
        "workload_weight": r.workload_weight,
        "default_required": r.default_required,
        "sort_order": r.sort_order,
        "active": r.active,
        "description": r.description,
    }


def _location_dict(r):
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "location_type": r.location_type,
        "parent_id": r.parent_id,
        "capacity": r.capacity,
        "sort_order": r.sort_order,
        "active": r.active,
        "notes": r.notes,
    }


def _teacher_dict(r):
    return {
        "id": r.id,
        "professor_name": r.professor_name,
        "employee_no": r.employee_no,
        "department": r.department,
        "max_total_duties": r.max_total_duties,
        "max_daily_duties": r.max_daily_duties,
        "active": r.active,
        "notes": r.notes,
    }


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    seed_defaults(db)
    rows = db.query(InvigilationDutyRole).order_by(
        InvigilationDutyRole.sort_order, InvigilationDutyRole.id
    ).all()
    return [_role_dict(r) for r in rows]


@router.post("/roles")
def create_role(payload: RoleInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    _validate_role_scope(payload.scope_type)
    if db.query(InvigilationDutyRole).filter(InvigilationDutyRole.code == payload.code).first():
        raise HTTPException(status_code=409, detail="岗位代码已存在")
    row = InvigilationDutyRole(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _role_dict(row)


@router.put("/roles/{role_id}")
def update_role(role_id: int, payload: RoleInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    _validate_role_scope(payload.scope_type)
    row = db.get(InvigilationDutyRole, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="岗位不存在")
    duplicate = db.query(InvigilationDutyRole).filter(
        InvigilationDutyRole.code == payload.code,
        InvigilationDutyRole.id != role_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="岗位代码已存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _role_dict(row)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    rows = db.query(InvigilationLocation).order_by(
        InvigilationLocation.sort_order, InvigilationLocation.id
    ).all()
    return [_location_dict(r) for r in rows]


def _validate_location_parent(db: Session, parent_id: Optional[int], row_id: Optional[int] = None):
    if parent_id is None:
        return
    if row_id is not None and parent_id == row_id:
        raise HTTPException(status_code=400, detail="地点不能把自己设为上级")
    if not db.get(InvigilationLocation, parent_id):
        raise HTTPException(status_code=400, detail="上级地点不存在")


@router.post("/locations")
def create_location(payload: LocationInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    _validate_location_type(payload.location_type)
    _validate_location_parent(db, payload.parent_id)
    if db.query(InvigilationLocation).filter(InvigilationLocation.code == payload.code).first():
        raise HTTPException(status_code=409, detail="地点代码已存在")
    row = InvigilationLocation(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _location_dict(row)


@router.put("/locations/{location_id}")
def update_location(location_id: int, payload: LocationInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    _validate_location_type(payload.location_type)
    _validate_location_parent(db, payload.parent_id, location_id)
    row = db.get(InvigilationLocation, location_id)
    if not row:
        raise HTTPException(status_code=404, detail="地点不存在")
    duplicate = db.query(InvigilationLocation).filter(
        InvigilationLocation.code == payload.code,
        InvigilationLocation.id != location_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="地点代码已存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _location_dict(row)


@router.get("/teachers")
def list_teacher_profiles(db: Session = Depends(get_db)):
    rows = db.query(InvigilationTeacherProfile).order_by(
        InvigilationTeacherProfile.professor_name
    ).all()
    return [_teacher_dict(r) for r in rows]


@router.post("/teachers")
def create_teacher_profile(payload: TeacherProfileInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(InvigilationTeacherProfile).filter(
        InvigilationTeacherProfile.professor_name == payload.professor_name
    ).first():
        raise HTTPException(status_code=409, detail="该人员已存在")
    if payload.employee_no and db.query(InvigilationTeacherProfile).filter(
        InvigilationTeacherProfile.employee_no == payload.employee_no
    ).first():
        raise HTTPException(status_code=409, detail="工号已存在")
    row = InvigilationTeacherProfile(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _teacher_dict(row)


@router.put("/teachers/{teacher_id}")
def update_teacher_profile(teacher_id: int, payload: TeacherProfileInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationTeacherProfile, teacher_id)
    if not row:
        raise HTTPException(status_code=404, detail="人员不存在")
    name_dup = db.query(InvigilationTeacherProfile).filter(
        InvigilationTeacherProfile.professor_name == payload.professor_name,
        InvigilationTeacherProfile.id != teacher_id,
    ).first()
    if name_dup:
        raise HTTPException(status_code=409, detail="姓名已存在")
    if payload.employee_no:
        no_dup = db.query(InvigilationTeacherProfile).filter(
            InvigilationTeacherProfile.employee_no == payload.employee_no,
            InvigilationTeacherProfile.id != teacher_id,
        ).first()
        if no_dup:
            raise HTTPException(status_code=409, detail="工号已存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _teacher_dict(row)


@router.get("/qualifications")
def list_qualifications(teacher_id: Optional[int] = None, db: Session = Depends(get_db)):
    seed_defaults(db)
    query = db.query(InvigilationTeacherRoleQualification)
    if teacher_id is not None:
        query = query.filter(InvigilationTeacherRoleQualification.teacher_profile_id == teacher_id)
    rows = query.all()
    return [{
        "id": r.id,
        "teacher_profile_id": r.teacher_profile_id,
        "duty_role_id": r.duty_role_id,
        "eligible": r.eligible,
    } for r in rows]


@router.post("/qualifications")
def upsert_qualification(payload: QualificationInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    teacher = db.get(InvigilationTeacherProfile, payload.teacher_profile_id)
    role = db.get(InvigilationDutyRole, payload.duty_role_id)
    if not teacher or not role:
        raise HTTPException(status_code=400, detail="人员或岗位不存在")
    row = db.query(InvigilationTeacherRoleQualification).filter(
        InvigilationTeacherRoleQualification.teacher_profile_id == payload.teacher_profile_id,
        InvigilationTeacherRoleQualification.duty_role_id == payload.duty_role_id,
    ).first()
    if row:
        row.eligible = payload.eligible
    else:
        row = InvigilationTeacherRoleQualification(**payload.model_dump())
        db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "teacher_profile_id": row.teacher_profile_id,
        "duty_role_id": row.duty_role_id,
        "eligible": row.eligible,
    }


@router.get("/unavailability")
def list_unavailability(teacher_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(InvigilationTeacherUnavailability)
    if teacher_id is not None:
        query = query.filter(InvigilationTeacherUnavailability.teacher_profile_id == teacher_id)
    rows = query.order_by(
        InvigilationTeacherUnavailability.date,
        InvigilationTeacherUnavailability.teacher_profile_id,
    ).all()
    return [{
        "id": r.id,
        "teacher_profile_id": r.teacher_profile_id,
        "date": r.date.isoformat(),
        "slot_code": r.slot_code,
        "reason": r.reason,
    } for r in rows]


@router.post("/unavailability")
def upsert_unavailability(payload: UnavailabilityInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not db.get(InvigilationTeacherProfile, payload.teacher_profile_id):
        raise HTTPException(status_code=400, detail="人员不存在")
    query = db.query(InvigilationTeacherUnavailability).filter(
        InvigilationTeacherUnavailability.teacher_profile_id == payload.teacher_profile_id,
        InvigilationTeacherUnavailability.date == payload.date,
    )
    row = (
        query.filter(InvigilationTeacherUnavailability.slot_code.is_(None)).first()
        if payload.slot_code is None
        else query.filter(InvigilationTeacherUnavailability.slot_code == payload.slot_code).first()
    )
    if not row:
        row = InvigilationTeacherUnavailability(**payload.model_dump())
        db.add(row)
    else:
        row.reason = payload.reason
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "teacher_profile_id": row.teacher_profile_id,
        "date": row.date.isoformat(),
        "slot_code": row.slot_code,
        "reason": row.reason,
    }


@router.delete("/unavailability/{item_id}")
def delete_unavailability(item_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(InvigilationTeacherUnavailability, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="不可用记录不存在")
    db.delete(row)
    db.commit()
    return {"success": True}


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    seed_defaults(db)
    rows = db.query(InvigilationRule).order_by(InvigilationRule.key).all()
    return [{
        "id": r.id,
        "key": r.key,
        "value": r.value,
        "value_type": r.value_type,
        "description": r.description,
    } for r in rows]


@router.put("/rules/{key}")
def update_rule(key: str, payload: RuleInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(InvigilationRule).filter(InvigilationRule.key == key).first()
    if not row:
        row = InvigilationRule(key=key, **payload.model_dump())
        db.add(row)
    else:
        row.value = payload.value
        row.value_type = payload.value_type
        row.description = payload.description
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "key": row.key,
        "value": row.value,
        "value_type": row.value_type,
        "description": row.description,
    }
