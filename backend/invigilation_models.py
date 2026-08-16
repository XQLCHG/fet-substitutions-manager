"""中国高校监考排班扩展数据模型。

该模块使用原项目 ``models.Base``，因此所有表继续落在每个学校自己的
``gestor.db`` 中，不改变现有 vigilancies/substitucions 表结构。

设计目标：
- 甲监、乙监、流动监考、巡考均为可配置岗位，而不是写死字段；
- 校区/考区/楼栋/楼层/考场使用一棵通用地点树；
- 人员资格、不可用时间和求解规则独立建模，为后续 OR-Tools CP-SAT 做准备。
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
    """参与监考排班的教师/工作人员扩展信息。

    professor_name 对接原项目中的教师姓名；后续 Excel 导入也写入此表。
    """

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
    """人员不可监考时间。

    slot_code 为空表示整天不可用；非空表示只屏蔽某个考试时段。
    """

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


class InvigilationRule(Base):
    """监考求解器规则配置。

    value 保存字符串形式，value_type 用于前端及求解器做可靠类型转换。
    """

    __tablename__ = "invigilation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(Text, nullable=False)
    value_type = Column(String, nullable=False, default="string")
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
