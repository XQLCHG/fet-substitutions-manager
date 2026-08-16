"""监考 Excel/PDF 报表基础回归测试。"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from invigilation_defaults import seed_defaults
from invigilation_models import (
    InvigilationAssignment,
    InvigilationDutyRole,
    InvigilationExamBatch,
    InvigilationExamSession,
    InvigilationLocation,
    InvigilationTeacherProfile,
)
from models import Base
from routes.invigilation_export import _assignment_rows, _content_disposition


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def test_export_query_and_unicode_safe_header():
    engine, db = _db()
    try:
        seed_defaults(db)
        primary = db.query(InvigilationDutyRole).filter(
            InvigilationDutyRole.code == "PRIMARY"
        ).one()
        room = InvigilationLocation(code="A101", name="A101", location_type="ROOM")
        batch = InvigilationExamBatch(name="期末考试")
        teacher = InvigilationTeacherProfile(
            professor_name="张三", employee_no="10001", department="计算机学院"
        )
        db.add_all([room, batch, teacher])
        db.flush()
        session = InvigilationExamSession(
            batch_id=batch.id,
            date=date(2026, 12, 25),
            slot_code="AM",
            slot_name="上午",
        )
        db.add(session)
        db.flush()
        db.add(InvigilationAssignment(
            session_id=session.id,
            location_id=room.id,
            duty_role_id=primary.id,
            teacher_profile_id=teacher.id,
            source="AUTO",
        ))
        db.commit()

        rows = _assignment_rows(db, batch.id)
        assert len(rows) == 1
        assert rows[0][4].professor_name == "张三"

        header = _content_disposition("invigilation.xlsx", "期末考试_监考安排.xlsx")
        header.encode("ascii")
        assert "filename*=UTF-8''" in header
        assert "%E6%9C%9F" in header
    finally:
        db.close()
        engine.dispose()
