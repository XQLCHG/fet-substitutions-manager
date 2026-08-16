"""中国高校监考扩展配置 API。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_utils import require_admin
from dependencies import get_db
from invigilation_models import (
    InvigilationDutyRole,
    InvigilationLocation,
    InvigilationRule,
    InvigilationTeacherProfile,
    InvigilationTeacherRoleQualification,
)

router = APIRouter(prefix="/api/invigilation", tags=["invigilation"])

DEFAULT_ROLES = [
    dict(code="PRIMARY", name="甲监", scope_type="ROOM", workload_weight=1.2, default_required=1, sort_order=10,
         description="固定考场主监考"),
    dict(code="SECONDARY", name="乙监", scope_type="ROOM", workload_weight=1.0, default_required=1, sort_order=20,
         description="固定考场副监考"),
    dict(code="ROVING", name="流动监考", scope_type="FLOOR", workload_weight=1.1, default_required=0, sort_order=30,
         description="负责楼层或区域内多个考场的流动监考"),
    dict(code="INSPECTOR", name="巡考", scope_type="AREA", workload_weight=1.3, default_required=0, sort_order=40,
         description="负责考区、楼栋或校区级巡视"),
]


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


def _seed_default_roles(db: Session):
    existing = {r.code for r in db.query(InvigilationDutyRole).all()}
    changed = False
    for item in DEFAULT_ROLES:
        if item["code"] not in existing:
            db.add(InvigilationDutyRole(**item))
            changed = True
    if changed:
        db.commit()


def _serialize_role(r):
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


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    _seed_default_roles(db)
    rows = db.query(InvigilationDutyRole).order_by(InvigilationDutyRole.sort_order, InvigilationDutyRole.id).all()
    return [_serialize_role(r) for r in rows]


@router.post("/roles")
def create_role(payload: RoleInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(InvigilationDutyRole).filter(InvigilationDutyRole.code == payload.code).first():
        raise HTTPException(status_code=409, detail="岗位代码已存在")
    row = InvigilationDutyRole(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_role(row)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    rows = db.query(InvigilationLocation).order_by(InvigilationLocation.sort_order, InvigilationLocation.id).all()
    return [{
        "id": r.id, "code": r.code, "name": r.name, "location_type": r.location_type,
        "parent_id": r.parent_id, "capacity": r.capacity, "sort_order": r.sort_order,
        "active": r.active, "notes": r.notes,
    } for r in rows]


@router.post("/locations")
def create_location(payload: LocationInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(InvigilationLocation).filter(InvigilationLocation.code == payload.code).first():
        raise HTTPException(status_code=409, detail="地点代码已存在")
    if payload.parent_id and not db.query(InvigilationLocation).filter(InvigilationLocation.id == payload.parent_id).first():
        raise HTTPException(status_code=400, detail="上级地点不存在")
    row = InvigilationLocation(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name, "location_type": row.location_type, "parent_id": row.parent_id}


@router.get("/teachers")
def list_teacher_profiles(db: Session = Depends(get_db)):
    rows = db.query(InvigilationTeacherProfile).order_by(InvigilationTeacherProfile.professor_name).all()
    return [{
        "id": r.id, "professor_name": r.professor_name, "employee_no": r.employee_no,
        "department": r.department, "max_total_duties": r.max_total_duties,
        "max_daily_duties": r.max_daily_duties, "active": r.active, "notes": r.notes,
    } for r in rows]


@router.post("/teachers")
def create_teacher_profile(payload: TeacherProfileInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(InvigilationTeacherProfile).filter(InvigilationTeacherProfile.professor_name == payload.professor_name).first():
        raise HTTPException(status_code=409, detail="该人员已存在")
    row = InvigilationTeacherProfile(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "professor_name": row.professor_name}


@router.get("/qualifications")
def list_qualifications(db: Session = Depends(get_db)):
    rows = db.query(InvigilationTeacherRoleQualification).all()
    return [{
        "id": r.id, "teacher_profile_id": r.teacher_profile_id,
        "duty_role_id": r.duty_role_id, "eligible": r.eligible,
    } for r in rows]


@router.post("/qualifications")
def upsert_qualification(payload: QualificationInput, db: Session = Depends(get_db), _=Depends(require_admin)):
    teacher = db.query(InvigilationTeacherProfile).filter(InvigilationTeacherProfile.id == payload.teacher_profile_id).first()
    role = db.query(InvigilationDutyRole).filter(InvigilationDutyRole.id == payload.duty_role_id).first()
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
    return {"id": row.id, "eligible": row.eligible}


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    rows = db.query(InvigilationRule).order_by(InvigilationRule.key).all()
    return [{"id": r.id, "key": r.key, "value": r.value, "value_type": r.value_type, "description": r.description} for r in rows]
