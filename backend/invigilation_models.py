"""中国高校监考排班扩展数据模型。

该模块使用原项目 ``models.Base``，因此所有表继续落在每个学校自己的
``gestor.db`` 中，不改变现有 vigilancies/substitucions 表结构。

设计目标：
- 甲监、乙监、流动监考、巡考均为可配置岗位，而不是写死字段；
- 校区/考区/楼栋/楼层/考场使用一棵通用地点树；
- 人员资格、不可用时间和求解规则独立建模；
- 考试批次、时段、考场考试和岗位需求直接作为后续 OR-Tools CP-SAT 输入。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from models import Base


ROLE_SCOPE_TYPES = ("ROOM", "FLOOR", "BUILDING", "AREA", "CAMPUS")
LOCATION_TYPES = ("ROOM", "FLOOR", "BUILDING", "AREA", "CAMPUS")


class InvigilationDutyRole(Base):
    """监考岗位。

    默认提供 PRIMARY/SECONDARY/ROVING/INSPECTOR 四种，但数据库允许继续新增
    主考、楼层负责人、备用监考等岗位。
    """

    __tablename__ = "invigilation_duty_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    scope_type = Column(String, nullable=False, default="ROOM")
    workload_weight = Column(Float, nullable=False, default=1.0)
    default_required = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_role_active", "active"),
        Index("idx_invigilation_role_sort", "sort_order"),
    )


class InvigilationLocation(Base):
    """监考地点树：校区 -> 考区 -> 楼栋 -> 楼层 -> 考场。"""

    __tablename__ = "invigilation_locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    location_type = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("invigilation_locations.id", ondelete="SET NULL"))
    capacity = Column(Integer)
    sort_order = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_location_parent", "parent_id"),
        Index("idx_invigilation_location_type", "location_type"),
        Index("idx_invigilation_location_active", "active"),
    )


class InvigilationTeacherProfile(Base):
    """参与监考排班的教师/工作人员扩展信息。"""

    __tablename__ = "invigilation_teacher_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    professor_name = Column(String, nullable=False, unique=True)
    employee_no = Column(String, unique=True)
    department = Column(String)
    max_total_duties = Column(Integer)
    max_daily_duties = Column(Integer, nullable=False, default=2)
    active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_teacher_department", "department"),
        Index("idx_invigilation_teacher_active", "active"),
    )


class InvigilationTeacherRoleQualification(Base):
    """某个人是否具备某监考岗位资格。"""

    __tablename__ = "invigilation_teacher_role_qualifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_profile_id = Column(
        Integer,
        ForeignKey("invigilation_teacher_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    duty_role_id = Column(
        Integer,
        ForeignKey("invigilation_duty_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    eligible = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "uq_invigilation_teacher_role",
            "teacher_profile_id",
            "duty_role_id",
            unique=True,
        ),
        Index("idx_invigilation_qualification_role", "duty_role_id"),
    )


class InvigilationTeacherUnavailability(Base):
    """人员不可监考时间；slot_code 为空表示整天不可用。"""

    __tablename__ = "invigilation_teacher_unavailability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_profile_id = Column(
        Integer,
        ForeignKey("invigilation_teacher_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(Date, nullable=False)
    slot_code = Column(String)
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_unavailable_teacher", "teacher_profile_id"),
        Index("idx_invigilation_unavailable_date", "date"),
        Index(
            "uq_invigilation_unavailable_slot",
            "teacher_profile_id",
            "date",
            "slot_code",
            unique=True,
        ),
    )


class InvigilationExamBatch(Base):
    """一次完整考试任务，例如“2026-2027 第一学期期末考试”。"""

    __tablename__ = "invigilation_exam_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    academic_year = Column(String)
    term = Column(String)
    status = Column(String, nullable=False, default="DRAFT")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_invigilation_batch_status", "status"),)


class InvigilationExamSession(Base):
    """考试日期 + 时段，例如 2026-12-25 上午。"""

    __tablename__ = "invigilation_exam_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(
        Integer,
        ForeignKey("invigilation_exam_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(Date, nullable=False)
    slot_code = Column(String, nullable=False)
    slot_name = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    sort_order = Column(Integer, nullable=False, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_session_batch", "batch_id"),
        Index("idx_invigilation_session_date", "date"),
        Index(
            "uq_invigilation_session_slot",
            "batch_id",
            "date",
            "slot_code",
            unique=True,
        ),
    )


class InvigilationExamRoom(Base):
    """某时段中的一场考场考试。

    room_location_id 必须指向 ROOM 类型地点；course_teacher_names 用于后续
    “任课教师回避本课程监考”等约束，使用逗号分隔以保持 SQLite 模型简单。
    """

    __tablename__ = "invigilation_exam_rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("invigilation_exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    room_location_id = Column(
        Integer,
        ForeignKey("invigilation_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    course_code = Column(String)
    course_name = Column(String, nullable=False)
    group_names = Column(Text)
    candidate_count = Column(Integer)
    department = Column(String)
    course_teacher_names = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_exam_room_session", "session_id"),
        Index("idx_invigilation_exam_room_location", "room_location_id"),
        Index(
            "uq_invigilation_exam_room_slot",
            "session_id",
            "room_location_id",
            unique=True,
        ),
    )


class InvigilationDutyRequirement(Base):
    """一个时段中某地点范围需要多少个某类监考岗位。

    示例：
    - A101 + PRIMARY + 1
    - A101 + SECONDARY + 1
    - 第一教学楼 2 层 + ROVING + 2
    - 第一考区 + INSPECTOR + 3
    """

    __tablename__ = "invigilation_duty_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("invigilation_exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id = Column(
        Integer,
        ForeignKey("invigilation_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    duty_role_id = Column(
        Integer,
        ForeignKey("invigilation_duty_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    required_count = Column(Integer, nullable=False, default=1)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_requirement_session", "session_id"),
        Index("idx_invigilation_requirement_location", "location_id"),
        Index("idx_invigilation_requirement_role", "duty_role_id"),
        Index(
            "uq_invigilation_requirement",
            "session_id",
            "location_id",
            "duty_role_id",
            unique=True,
        ),
    )


class InvigilationAssignment(Base):
    """监考分配结果。

    Phase 03 的求解器会写入此表；locked=True 的记录在局部重排时必须保持。
    """

    __tablename__ = "invigilation_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("invigilation_exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id = Column(
        Integer,
        ForeignKey("invigilation_locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    duty_role_id = Column(
        Integer,
        ForeignKey("invigilation_duty_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    teacher_profile_id = Column(
        Integer,
        ForeignKey("invigilation_teacher_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String, nullable=False, default="AUTO")
    locked = Column(Boolean, nullable=False, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_invigilation_assignment_session", "session_id"),
        Index("idx_invigilation_assignment_teacher", "teacher_profile_id"),
        Index("idx_invigilation_assignment_locked", "locked"),
        Index(
            "uq_invigilation_assignment_teacher_slot",
            "session_id",
            "teacher_profile_id",
            unique=True,
        ),
    )


class InvigilationRule(Base):
    """监考求解器规则配置。"""

    __tablename__ = "invigilation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(Text, nullable=False)
    value_type = Column(String, nullable=False, default="string")
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
