"""CP-SAT 监考排班核心回归测试。"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from invigilation_defaults import seed_defaults
from invigilation_engine import solve_batch
from invigilation_models import (
    InvigilationDutyRequirement,
    InvigilationDutyRole,
    InvigilationExamBatch,
    InvigilationExamRoom,
    InvigilationExamSession,
    InvigilationLocation,
    InvigilationTeacherProfile,
    InvigilationTeacherRoleQualification,
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


def _build_case(db, teacher_count=4):
    seed_defaults(db)
    roles = {r.code: r for r in db.query(InvigilationDutyRole).all()}
    room = InvigilationLocation(code="A101", name="A101", location_type="ROOM")
    batch = InvigilationExamBatch(name="期末考试")
    db.add_all([room, batch])
    db.flush()
    session = InvigilationExamSession(
        batch_id=batch.id,
        date=date(2026, 12, 25),
        slot_code="AM",
        slot_name="上午",
    )
    db.add(session)
    db.flush()
    db.add(InvigilationExamRoom(
        session_id=session.id,
        room_location_id=room.id,
        course_name="高等数学",
    ))
    db.add_all([
        InvigilationDutyRequirement(
            session_id=session.id,
            location_id=room.id,
            duty_role_id=roles["PRIMARY"].id,
            required_count=1,
        ),
        InvigilationDutyRequirement(
            session_id=session.id,
            location_id=room.id,
            duty_role_id=roles["SECONDARY"].id,
            required_count=1,
        ),
    ])
    for idx in range(teacher_count):
        teacher = InvigilationTeacherProfile(
            professor_name=f"教师{idx + 1}",
            employee_no=f"T{idx + 1:03d}",
            max_daily_duties=2,
        )
        db.add(teacher)
        db.flush()
        db.add_all([
            InvigilationTeacherRoleQualification(
                teacher_profile_id=teacher.id,
                duty_role_id=roles["PRIMARY"].id,
                eligible=True,
            ),
            InvigilationTeacherRoleQualification(
                teacher_profile_id=teacher.id,
                duty_role_id=roles["SECONDARY"].id,
                eligible=True,
            ),
        ])
    db.commit()
    return batch


def test_solver_fills_primary_and_secondary_with_different_people(db):
    batch = _build_case(db, teacher_count=4)
    result = solve_batch(db, batch.id, persist=False)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert result["assignment_count"] == 2
    assert {a["role_code"] for a in result["assignments"]} == {"PRIMARY", "SECONDARY"}
    assert len({a["teacher_profile_id"] for a in result["assignments"]}) == 2


def test_solver_reports_session_staff_shortage_before_solving(db):
    batch = _build_case(db, teacher_count=1)
    result = solve_batch(db, batch.id, persist=False)
    assert result["status"] == "INFEASIBLE_PRECHECK"
    kinds = {item["kind"] for item in result["diagnostics"]}
    assert "SESSION_STAFF_SHORTAGE" in kinds
