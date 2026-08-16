"""中国监考模块默认配置。"""
from sqlalchemy.orm import Session

from invigilation_models import InvigilationDutyRole, InvigilationRule


DEFAULT_ROLES = [
    dict(code="PRIMARY", name="甲监", scope_type="ROOM", workload_weight=1.2,
         default_required=1, sort_order=10, description="固定考场主监考"),
    dict(code="SECONDARY", name="乙监", scope_type="ROOM", workload_weight=1.0,
         default_required=1, sort_order=20, description="固定考场副监考"),
    dict(code="ROVING", name="流动监考", scope_type="FLOOR", workload_weight=1.1,
         default_required=0, sort_order=30, description="负责楼层或区域内多个考场的流动监考"),
    dict(code="INSPECTOR", name="巡考", scope_type="AREA", workload_weight=1.3,
         default_required=0, sort_order=40, description="负责考区、楼栋或校区级巡视"),
]

DEFAULT_RULES = [
    dict(key="avoid_course_teacher", value="true", value_type="bool",
         description="任课教师默认回避自己课程的考场监考"),
    dict(key="max_daily_duties_default", value="2", value_type="int",
         description="未单独设置人员上限时，每人每天最多监考场次"),
    dict(key="avoid_consecutive_duties", value="true", value_type="bool",
         description="尽量避免连续时段监考"),
    dict(key="fairness_weight", value="100", value_type="int",
         description="加权工作量公平性的优化权重"),
    dict(key="consecutive_penalty", value="20", value_type="int",
         description="连续监考软约束惩罚"),
    dict(key="stability_reward", value="10", value_type="int",
         description="重新排班时保留原未锁定分配的奖励，减少无意义换人"),
    dict(key="solver_time_limit_seconds", value="30", value_type="int",
         description="CP-SAT 单次求解最大时间（秒）"),
    dict(key="solver_workers", value="8", value_type="int",
         description="CP-SAT 并行搜索 worker 数量"),
]


def seed_defaults(db: Session) -> None:
    """幂等写入默认岗位和基础规则。"""
    role_codes = {r.code for r in db.query(InvigilationDutyRole).all()}
    rule_keys = {r.key for r in db.query(InvigilationRule).all()}
    changed = False

    for item in DEFAULT_ROLES:
        if item["code"] not in role_codes:
            db.add(InvigilationDutyRole(**item))
            changed = True

    for item in DEFAULT_RULES:
        if item["key"] not in rule_keys:
            db.add(InvigilationRule(**item))
            changed = True

    if changed:
        db.commit()
