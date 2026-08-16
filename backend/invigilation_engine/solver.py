"""基于 OR-Tools CP-SAT 的监考自动排班内核。"""
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from invigilation_defaults import seed_defaults
from invigilation_models import (
    InvigilationAssignment,
    InvigilationDutyRequirement,
    InvigilationDutyRole,
    InvigilationExamBatch,
    InvigilationExamRoom,
    InvigilationExamSession,
    InvigilationLocation,
    InvigilationRule,
    InvigilationTeacherProfile,
    InvigilationTeacherRoleQualification,
    InvigilationTeacherUnavailability,
)

WEIGHT_SCALE = 100


def _split_names(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    normalized = value
    for separator in ("，", ";", "；", "、", "|"):
        normalized = normalized.replace(separator, ",")
    return {part.strip() for part in normalized.split(",") if part.strip()}


def _rule_values(db: Session) -> Dict[str, object]:
    seed_defaults(db)
    result: Dict[str, object] = {}
    for row in db.query(InvigilationRule).all():
        if row.value_type == "bool":
            result[row.key] = str(row.value).strip().lower() in {"1", "true", "yes", "是"}
        elif row.value_type == "int":
            try:
                result[row.key] = int(row.value)
            except (TypeError, ValueError):
                result[row.key] = 0
        elif row.value_type == "float":
            try:
                result[row.key] = float(row.value)
            except (TypeError, ValueError):
                result[row.key] = 0.0
        else:
            result[row.key] = row.value
    return result


def _historical_stats(db: Session, batch_id: int, roles: Dict[int, InvigilationDutyRole]):
    counts = defaultdict(int)
    weighted = defaultdict(int)
    rows = (
        db.query(InvigilationAssignment, InvigilationExamSession)
        .join(InvigilationExamSession, InvigilationAssignment.session_id == InvigilationExamSession.id)
        .filter(InvigilationExamSession.batch_id != batch_id)
        .all()
    )
    for assignment, _session in rows:
        counts[assignment.teacher_profile_id] += 1
        role = roles.get(assignment.duty_role_id)
        if role:
            weighted[assignment.teacher_profile_id] += round(role.workload_weight * WEIGHT_SCALE)
    return counts, weighted


def _serialize_diagnostic(kind: str, message: str, **extra):
    item = {"kind": kind, "message": message}
    item.update(extra)
    return item


def solve_batch(
    db: Session,
    batch_id: int,
    *,
    persist: bool = True,
    replace_unlocked: bool = True,
) -> dict:
    """求解一个考试批次的监考分配。

    Hard constraints:
    - 每个岗位需求必须精确满足；
    - 同一老师同一考试时段最多一个岗位；
    - 岗位资格、不可用时间、每日/总场次上限必须满足；
    - 任课教师默认回避自己课程的甲监/乙监；
    - locked=True 的现有分配必须保持。

    Soft constraints:
    - 最小化全体候选人的加权工作量极差；
    - 尽量减少连续时段监考；
    - 局部重排时尽量保留原有未锁定分配，降低通知变更量。
    """
    seed_defaults(db)
    batch = db.get(InvigilationExamBatch, batch_id)
    if not batch:
        return {"status": "NOT_FOUND", "message": "考试批次不存在", "batch_id": batch_id}

    rules = _rule_values(db)
    sessions = (
        db.query(InvigilationExamSession)
        .filter(InvigilationExamSession.batch_id == batch_id)
        .order_by(InvigilationExamSession.date, InvigilationExamSession.sort_order,
                  InvigilationExamSession.slot_code)
        .all()
    )
    session_ids = [s.id for s in sessions]
    if not session_ids:
        return {"status": "EMPTY", "message": "该批次没有考试时段", "batch_id": batch_id}

    requirements = (
        db.query(InvigilationDutyRequirement)
        .filter(InvigilationDutyRequirement.session_id.in_(session_ids))
        .all()
    )
    if not requirements:
        return {"status": "EMPTY", "message": "该批次没有监考岗位需求", "batch_id": batch_id}

    teachers = db.query(InvigilationTeacherProfile).filter(
        InvigilationTeacherProfile.active.is_(True)
    ).all()
    if not teachers:
        return {"status": "INFEASIBLE_PRECHECK", "message": "没有可参与排班的人员", "diagnostics": []}

    teacher_by_id = {t.id: t for t in teachers}
    session_by_id = {s.id: s for s in sessions}
    roles = {r.id: r for r in db.query(InvigilationDutyRole).all()}
    locations = {r.id: r for r in db.query(InvigilationLocation).all()}
    requirement_by_key = {
        (r.session_id, r.location_id, r.duty_role_id): r for r in requirements
    }

    qualifications = defaultdict(set)
    qualification_row_count = defaultdict(int)
    for q in db.query(InvigilationTeacherRoleQualification).all():
        qualification_row_count[q.teacher_profile_id] += 1
        if q.eligible:
            qualifications[q.teacher_profile_id].add(q.duty_role_id)

    unavailable_day = set()
    unavailable_slot = set()
    for row in db.query(InvigilationTeacherUnavailability).all():
        if row.slot_code:
            unavailable_slot.add((row.teacher_profile_id, row.date, row.slot_code))
        else:
            unavailable_day.add((row.teacher_profile_id, row.date))

    exam_room_by_key = {
        (r.session_id, r.room_location_id): r
        for r in db.query(InvigilationExamRoom).filter(
            InvigilationExamRoom.session_id.in_(session_ids)
        ).all()
    }

    all_target_assignments = (
        db.query(InvigilationAssignment)
        .filter(InvigilationAssignment.session_id.in_(session_ids))
        .all()
    )
    fixed_assignments = [a for a in all_target_assignments if a.locked or not replace_unlocked]
    historical_counts, historical_weighted = _historical_stats(db, batch_id, roles)

    def qualified(teacher: InvigilationTeacherProfile, role: InvigilationDutyRole) -> bool:
        if qualification_row_count[teacher.id] == 0:
            return role.code in {"PRIMARY", "SECONDARY"}
        return role.id in qualifications[teacher.id]

    def available(teacher: InvigilationTeacherProfile, session: InvigilationExamSession) -> bool:
        if (teacher.id, session.date) in unavailable_day:
            return False
        return (teacher.id, session.date, session.slot_code) not in unavailable_slot

    def avoids_course(teacher: InvigilationTeacherProfile, requirement: InvigilationDutyRequirement,
                      role: InvigilationDutyRole) -> bool:
        if not rules.get("avoid_course_teacher", True):
            return False
        if role.code not in {"PRIMARY", "SECONDARY"}:
            return False
        exam_room = exam_room_by_key.get((requirement.session_id, requirement.location_id))
        if not exam_room:
            return False
        return teacher.professor_name in _split_names(exam_room.course_teacher_names)

    candidates: Dict[int, List[int]] = {}
    diagnostics: List[dict] = []
    for req in requirements:
        role = roles.get(req.duty_role_id)
        location = locations.get(req.location_id)
        session = session_by_id.get(req.session_id)
        if not role or not location or not session:
            diagnostics.append(_serialize_diagnostic(
                "BROKEN_REQUIREMENT", "岗位需求引用了不存在的数据", requirement_id=req.id
            ))
            candidates[req.id] = []
            continue
        if role.scope_type != location.location_type:
            diagnostics.append(_serialize_diagnostic(
                "SCOPE_MISMATCH",
                f"{role.name} 要求 {role.scope_type} 范围，但地点 {location.name} 是 {location.location_type}",
                requirement_id=req.id,
            ))
        allowed = []
        for teacher in teachers:
            if not qualified(teacher, role):
                continue
            if not available(teacher, session):
                continue
            if avoids_course(teacher, req, role):
                continue
            if teacher.max_total_duties is not None and historical_counts[teacher.id] >= teacher.max_total_duties:
                continue
            allowed.append(teacher.id)
        candidates[req.id] = allowed
        if len(allowed) < req.required_count:
            diagnostics.append(_serialize_diagnostic(
                "ROLE_SHORTAGE",
                f"{session.date} {session.slot_name or session.slot_code} / {location.name} / {role.name} "
                f"需要 {req.required_count} 人，但只有 {len(allowed)} 名合格可用人员",
                requirement_id=req.id,
                required=req.required_count,
                candidates=len(allowed),
                role=role.name,
                location=location.name,
                session_id=session.id,
            ))

    fixed_by_req = defaultdict(list)
    for assignment in fixed_assignments:
        req = requirement_by_key.get(
            (assignment.session_id, assignment.location_id, assignment.duty_role_id)
        )
        if not req:
            diagnostics.append(_serialize_diagnostic(
                "LOCKED_WITHOUT_REQUIREMENT",
                "锁定分配已经没有对应岗位需求",
                assignment_id=assignment.id,
            ))
            continue
        fixed_by_req[req.id].append(assignment)
        if assignment.teacher_profile_id not in candidates.get(req.id, []):
            teacher = teacher_by_id.get(assignment.teacher_profile_id)
            diagnostics.append(_serialize_diagnostic(
                "INVALID_LOCK",
                f"锁定人员 {teacher.professor_name if teacher else assignment.teacher_profile_id} "
                "不再满足该岗位当前资格/可用性约束",
                assignment_id=assignment.id,
                requirement_id=req.id,
            ))

    for req in requirements:
        if len(fixed_by_req[req.id]) > req.required_count:
            diagnostics.append(_serialize_diagnostic(
                "TOO_MANY_LOCKS",
                "某岗位锁定人数超过岗位需求人数",
                requirement_id=req.id,
                locked=len(fixed_by_req[req.id]),
                required=req.required_count,
            ))

    reqs_by_session = defaultdict(list)
    for req in requirements:
        reqs_by_session[req.session_id].append(req)
    for session_id, reqs in reqs_by_session.items():
        unique = set()
        required_total = 0
        for req in reqs:
            unique.update(candidates.get(req.id, []))
            required_total += req.required_count
        if len(unique) < required_total:
            session = session_by_id[session_id]
            diagnostics.append(_serialize_diagnostic(
                "SESSION_STAFF_SHORTAGE",
                f"{session.date} {session.slot_name or session.slot_code} 共需 {required_total} 个岗位，"
                f"但整个时段最多只有 {len(unique)} 名不同人员可用",
                session_id=session_id,
                required=required_total,
                candidates=len(unique),
            ))

    fatal_kinds = {
        "BROKEN_REQUIREMENT", "SCOPE_MISMATCH", "ROLE_SHORTAGE", "INVALID_LOCK",
        "LOCKED_WITHOUT_REQUIREMENT", "TOO_MANY_LOCKS", "SESSION_STAFF_SHORTAGE",
    }
    if any(d["kind"] in fatal_kinds for d in diagnostics):
        return {
            "status": "INFEASIBLE_PRECHECK",
            "batch_id": batch_id,
            "message": "排班前检查发现不可满足的硬约束",
            "diagnostics": diagnostics,
        }

    model = cp_model.CpModel()
    variables: Dict[Tuple[int, int], cp_model.IntVar] = {}
    vars_by_teacher_session = defaultdict(list)
    vars_by_teacher_date = defaultdict(list)
    vars_by_teacher = defaultdict(list)

    for req in requirements:
        session = session_by_id[req.session_id]
        for teacher_id in candidates[req.id]:
            var = model.new_bool_var(f"a_t{teacher_id}_r{req.id}")
            variables[(teacher_id, req.id)] = var
            vars_by_teacher_session[(teacher_id, req.session_id)].append(var)
            vars_by_teacher_date[(teacher_id, session.date)].append(var)
            vars_by_teacher[teacher_id].append((var, req))

    for req in requirements:
        model.add(sum(variables[(tid, req.id)] for tid in candidates[req.id]) == req.required_count)

    for _key, vars_list in vars_by_teacher_session.items():
        model.add(sum(vars_list) <= 1)

    default_daily = int(rules.get("max_daily_duties_default", 2) or 2)
    for teacher in teachers:
        daily_limit = teacher.max_daily_duties if teacher.max_daily_duties is not None else default_daily
        for session_date in {s.date for s in sessions}:
            day_vars = vars_by_teacher_date.get((teacher.id, session_date), [])
            if day_vars:
                model.add(sum(day_vars) <= daily_limit)
        if teacher.max_total_duties is not None:
            target_vars = [var for var, _req in vars_by_teacher.get(teacher.id, [])]
            if target_vars:
                model.add(sum(target_vars) + historical_counts[teacher.id] <= teacher.max_total_duties)

    for assignment in fixed_assignments:
        req = requirement_by_key[(assignment.session_id, assignment.location_id, assignment.duty_role_id)]
        model.add(variables[(assignment.teacher_profile_id, req.id)] == 1)

    objective_terms = []
    fairness_weight = int(rules.get("fairness_weight", 100) or 0)
    fairness_teacher_ids = [tid for tid, entries in vars_by_teacher.items() if entries]
    workload_vars = []
    if fairness_weight > 0 and fairness_teacher_ids:
        max_role_weight = max(round(r.workload_weight * WEIGHT_SCALE) for r in roles.values())
        total_positions = sum(r.required_count for r in requirements)
        upper = max(historical_weighted.values(), default=0) + max_role_weight * total_positions + 1
        for teacher_id in fairness_teacher_ids:
            workload = model.new_int_var(0, upper, f"workload_t{teacher_id}")
            weighted_terms = [
                var * round(roles[req.duty_role_id].workload_weight * WEIGHT_SCALE)
                for var, req in vars_by_teacher[teacher_id]
            ]
            model.add(workload == historical_weighted[teacher_id] + sum(weighted_terms))
            workload_vars.append(workload)
        if len(workload_vars) >= 2:
            max_workload = model.new_int_var(0, upper, "max_workload")
            min_workload = model.new_int_var(0, upper, "min_workload")
            model.add_max_equality(max_workload, workload_vars)
            model.add_min_equality(min_workload, workload_vars)
            objective_terms.append(fairness_weight * (max_workload - min_workload))

    if rules.get("avoid_consecutive_duties", True):
        consecutive_penalty = int(rules.get("consecutive_penalty", 20) or 0)
        sessions_by_date = defaultdict(list)
        for session in sessions:
            sessions_by_date[session.date].append(session)
        for same_day_sessions in sessions_by_date.values():
            same_day_sessions.sort(key=lambda s: (s.sort_order, s.slot_code))
            for first, second in zip(same_day_sessions, same_day_sessions[1:]):
                for teacher_id in fairness_teacher_ids:
                    first_vars = vars_by_teacher_session.get((teacher_id, first.id), [])
                    second_vars = vars_by_teacher_session.get((teacher_id, second.id), [])
                    if not first_vars or not second_vars:
                        continue
                    both = model.new_bool_var(f"consecutive_t{teacher_id}_s{first.id}_{second.id}")
                    first_expr = sum(first_vars)
                    second_expr = sum(second_vars)
                    model.add(both <= first_expr)
                    model.add(both <= second_expr)
                    model.add(both >= first_expr + second_expr - 1)
                    objective_terms.append(consecutive_penalty * both)

    stability_reward = int(rules.get("stability_reward", 10) or 0)
    if replace_unlocked and stability_reward > 0:
        for assignment in all_target_assignments:
            if assignment.locked:
                continue
            req = requirement_by_key.get(
                (assignment.session_id, assignment.location_id, assignment.duty_role_id)
            )
            if req and (assignment.teacher_profile_id, req.id) in variables:
                objective_terms.append(-stability_reward * variables[(assignment.teacher_profile_id, req.id)])

    if objective_terms:
        model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1, int(rules.get("solver_time_limit_seconds", 30) or 30))
    solver.parameters.num_search_workers = max(1, int(rules.get("solver_workers", 8) or 8))
    solver.parameters.random_seed = 1
    status = solver.solve(model)

    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": status_name,
            "batch_id": batch_id,
            "message": "CP-SAT 未找到可行排班" if status == cp_model.INFEASIBLE else "求解在限制时间内未得到可行结果",
            "diagnostics": diagnostics,
            "stats": {
                "wall_time": solver.wall_time,
                "conflicts": solver.num_conflicts,
                "branches": solver.num_branches,
            },
        }

    selected = []
    fixed_keys = {
        (a.teacher_profile_id, a.session_id, a.location_id, a.duty_role_id): a
        for a in fixed_assignments
    }
    for req in requirements:
        role = roles[req.duty_role_id]
        location = locations[req.location_id]
        session = session_by_id[req.session_id]
        for teacher_id in candidates[req.id]:
            var = variables[(teacher_id, req.id)]
            if solver.value(var) != 1:
                continue
            teacher = teacher_by_id[teacher_id]
            fixed = fixed_keys.get((teacher_id, req.session_id, req.location_id, req.duty_role_id))
            selected.append({
                "teacher_profile_id": teacher_id,
                "teacher_name": teacher.professor_name,
                "session_id": session.id,
                "date": session.date.isoformat(),
                "slot_code": session.slot_code,
                "slot_name": session.slot_name,
                "location_id": location.id,
                "location_name": location.name,
                "duty_role_id": role.id,
                "role_code": role.code,
                "role_name": role.name,
                "locked": bool(fixed and fixed.locked),
            })

    if persist:
        if replace_unlocked:
            db.query(InvigilationAssignment).filter(
                InvigilationAssignment.session_id.in_(session_ids),
                InvigilationAssignment.locked.is_(False),
            ).delete(synchronize_session=False)
        for item in selected:
            key = (
                item["teacher_profile_id"], item["session_id"],
                item["location_id"], item["duty_role_id"],
            )
            if key in fixed_keys:
                continue
            db.add(InvigilationAssignment(
                session_id=item["session_id"],
                location_id=item["location_id"],
                duty_role_id=item["duty_role_id"],
                teacher_profile_id=item["teacher_profile_id"],
                source="AUTO_REPLAN" if all_target_assignments else "AUTO",
                locked=False,
            ))
        db.commit()

    weighted_load = defaultdict(float)
    for item in selected:
        weighted_load[item["teacher_profile_id"]] += roles[item["duty_role_id"]].workload_weight

    return {
        "status": status_name,
        "batch_id": batch_id,
        "persisted": persist,
        "assignment_count": len(selected),
        "assignments": selected,
        "diagnostics": diagnostics,
        "workload": [
            {
                "teacher_profile_id": tid,
                "teacher_name": teacher_by_id[tid].professor_name,
                "batch_weighted_load": round(load, 3),
                "historical_weighted_load": round(historical_weighted[tid] / WEIGHT_SCALE, 3),
            }
            for tid, load in sorted(weighted_load.items(), key=lambda x: teacher_by_id[x[0]].professor_name)
        ],
        "stats": {
            "objective": solver.objective_value if objective_terms else 0,
            "wall_time": solver.wall_time,
            "conflicts": solver.num_conflicts,
            "branches": solver.num_branches,
        },
    }
