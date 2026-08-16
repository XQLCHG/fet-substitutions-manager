"""Phase 02 回归测试：监考领域模型的关键唯一约束。"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from invigilation_defaults import seed_defaults
from invigilation_models import (
    InvigilationAssignment,
    InvigilationDutyRequirement,
    InvigilationDutyRole,
    InvigilationExamBatch,
    InvigilationExamRoom,
    InvigilationExamSession,
    InvigilationLocation,
    InvigilationTeacherProfile,
)
from models import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _basic_data(db):
    seed_defaults(db)
    roles = {r.code: r for r in db.query(InvigilationDutyRole).all()}

    area = InvigilationLocation(code="AREA-1", name="第一考区", location_type="AREA")
    floor = InvigilationLocation(code="FLOOR-1", name="1层", location_type="FLOOR")
    room = InvigilationLocation(code="ROOM-A101", name="A101", location_type="ROOM")
    db.add_all([area, floor, room])

    batch = InvigilationExamBatch(name="期末考试", academic_year="2026-2027")
    teacher = InvigilationTeacherProfile(professor_name="张三", employee_no="10001")
    db.add_all([batch, teacher])
    db.flush()

    session = InvigilationExamSession(
        batch_id=batch.id,
        date=date(2026, 12, 25),
        slot_code="AM",
        slot_name="上午",
    )
    db.add(session)
    db.commit()
    return roles, area, floor, room, batch, teacher, session


def test_seed_default_roles(db):
    seed_defaults(db)
    roles = {r.code: r for r in db.query(InvigilationDutyRole).all()}
    assert set(roles) >= {"PRIMARY", "SECONDARY", "ROVING", "INSPECTOR"}
    assert roles["PRIMARY"].name == "甲监"
    assert roles["SECONDARY"].name == "乙监"
    assert roles["ROVING"].scope_type == "FLOOR"
    assert roles["INSPECTOR"].scope_type == "AREA"


def test_one_exam_per_room_per_session(db):
    roles, area, floor, room, batch, teacher, session = _basic_data(db)
    db.add(InvigilationExamRoom(
        session_id=session.id,
        room_location_id=room.id,
        course_name="高等数学",
    ))
    db.commit()

    db.add(InvigilationExamRoom(
        session_id=session.id,
        room_location_id=room.id,
        course_name="大学英语",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_requirement_unique_per_session_location_role(db):
    roles, area, floor, room, batch, teacher, session = _basic_data(db)
    db.add(InvigilationDutyRequirement(
        session_id=session.id,
        location_id=room.id,
        duty_role_id=roles["PRIMARY"].id,
        required_count=1,
    ))
    db.commit()

    db.add(InvigilationDutyRequirement(
        session_id=session.id,
        location_id=room.id,
        duty_role_id=roles["PRIMARY"].id,
        required_count=2,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_teacher_cannot_hold_two_duties_in_same_session(db):
    roles, area, floor, room, batch, teacher, session = _basic_data(db)
    db.add(InvigilationAssignment(
        session_id=session.id,
        location_id=room.id,
        duty_role_id=roles["PRIMARY"].id,
        teacher_profile_id=teacher.id,
    ))
    db.commit()

    db.add(InvigilationAssignment(
        session_id=session.id,
        location_id=room.id,
        duty_role_id=roles["SECONDARY"].id,
        teacher_profile_id=teacher.id,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
