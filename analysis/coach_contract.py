from copy import deepcopy


ANALYSIS_SCHEMA_VERSION = 4
FORBIDDEN_COACH_TERMS = (
    "人工",
    "手动",
    "回放",
    "回顾",
    "推断",
    "推测",
    "猜",
    "可能",
    "大概",
    "职业平均",
    "职业均值",
)


class CoachValidationError(ValueError):
    pass


def actionable_findings(analysis):
    findings = []
    for item in analysis.get("review_findings", []) if isinstance(analysis, dict) else []:
        if not isinstance(item, dict):
            continue
        success_metric = str(item.get("success_metric") or "")
        action = str(item.get("action") or "")
        training_goal = str(item.get("training_goal") or "")
        if success_metric.startswith("数据验收："):
            continue
        if any(
            marker in action or marker in training_goal
            for marker in ("系统会继续请求", "后续抓取", "先保证系统拿到")
        ):
            continue
        findings.append(item)
    return findings


def _finding_group(category):
    category = str(category or "")
    if category.startswith("death_") or category == "death_review":
        return "death"
    if category in {"lane_farm", "resource_continuity"}:
        return "resource"
    if category in {"item_timing"}:
        return "item"
    if category in {"closing", "map_impact"}:
        return "map"
    if category in {"support_vision"}:
        return "vision"
    return category or "other"


def select_coaching_findings(analysis, limit=4):
    priority_weight = {"high": 3, "medium": 2, "low": 1}
    category_weight = {
        "death_objective_window": 100,
        "death_review": 95,
        "death_recovery": 90,
        "death_resource_overlap": 85,
        "death_resource_delta": 80,
        "death_position_pattern": 75,
        "item_timing": 70,
        "lane_farm": 65,
        "resource_continuity": 60,
        "map_impact": 55,
        "hero_benchmark_gap": 50,
    }
    indexed = list(enumerate(actionable_findings(analysis)))
    indexed.sort(key=lambda pair: (
        -priority_weight.get(pair[1].get("priority"), 0),
        -category_weight.get(pair[1].get("category"), 0),
        pair[0],
    ))

    selected = []
    deferred = []
    groups = set()
    group_counts = {}
    for _, finding in indexed:
        group = _finding_group(finding.get("category"))
        if group in groups:
            deferred.append(finding)
            continue
        groups.add(group)
        group_counts[group] = 1
        selected.append(finding)
        if len(selected) >= limit:
            return selected
    for finding in deferred:
        group = _finding_group(finding.get("category"))
        if group_counts.get(group, 0) >= 2:
            continue
        group_counts[group] = group_counts.get(group, 0) + 1
        selected.append(finding)
        if len(selected) >= limit:
            break
    return selected


def build_coach_payload(analysis, hero_name, is_win):
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "hero_name": hero_name,
        "is_win": bool(is_win),
        "duration_min": analysis.get("duration_min"),
        "kda": deepcopy(analysis.get("kda") or {}),
        "farm": deepcopy(analysis.get("farm") or {}),
        "derived": deepcopy(analysis.get("derived") or {}),
        "role_profile": deepcopy(analysis.get("role_profile") or {}),
        "timeline": deepcopy(analysis.get("timeline") or {}),
        "events": deepcopy(analysis.get("events") or {}),
        "review_findings": deepcopy(select_coaching_findings(analysis)),
        "data_quality": deepcopy(analysis.get("data_quality") or {}),
    }


def deterministic_coach(analysis, preserve_order=False):
    findings = (
        actionable_findings(analysis)[:4]
        if preserve_order
        else select_coaching_findings(analysis)
    )
    if findings:
        top = findings[0]
        label = top.get("category_label") or top.get("category") or "本局重点"
        evidence = top.get("evidence") or "已有确定性证据"
        conclusion = f"{label}是本局首要复盘点：{evidence}"
    else:
        conclusion = "当前证据没有形成可发布的问题结论，本局只保留事实数据。"

    review_points = []
    next_actions = []
    for finding in findings:
        review_points.append({
            "category": finding.get("category"),
            "title": finding.get("category_label") or finding.get("category"),
            "priority": finding.get("priority"),
            "evidence": finding.get("evidence"),
            "why_it_matters": finding.get("why_it_matters"),
            "action": finding.get("action"),
            "system_check": finding.get("replay_check"),
        })
        next_actions.append({
            "category": finding.get("category"),
            "title": finding.get("category_label") or finding.get("category"),
            "action": finding.get("action"),
            "training_goal": finding.get("training_goal"),
            "success_metric": finding.get("success_metric"),
        })

    return {
        "conclusion": conclusion,
        "review_points": review_points,
        "next_actions": next_actions,
        "data_limits": list((analysis.get("data_quality") or {}).get("limitations") or []),
        "ai_ranked": False,
    }


def rank_coach_from_ai(payload, analysis):
    if not isinstance(payload, dict):
        raise CoachValidationError("AI ranking payload must be an object")
    findings = select_coaching_findings(analysis)
    order = payload.get("finding_order")
    if not isinstance(order, list):
        raise CoachValidationError("AI ranking is missing finding_order")
    if any(isinstance(index, bool) or not isinstance(index, int) for index in order):
        raise CoachValidationError("AI ranking indexes must be integers")
    expected = list(range(len(findings)))
    if len(order) != len(expected) or sorted(order) != expected:
        raise CoachValidationError("AI ranking must include every finding index exactly once")

    ranked_analysis = dict(analysis)
    ranked_analysis["review_findings"] = [findings[index] for index in order]
    coach = deterministic_coach(ranked_analysis, preserve_order=True)
    coach["ai_ranked"] = True
    return coach


def _required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise CoachValidationError(f"AI coach field is missing: {field}")
    if any(term in value for term in FORBIDDEN_COACH_TERMS):
        raise CoachValidationError(f"AI coach field contains unsupported language: {field}")
    return value.strip()


def validate_coach_payload(payload, findings):
    if not isinstance(payload, dict):
        raise CoachValidationError("AI coach payload must be an object")
    source_findings = {
        item.get("category"): item
        for item in findings or []
        if isinstance(item, dict) and item.get("category")
    }
    conclusion = _required_text(payload.get("conclusion"), "conclusion")
    review_points = payload.get("review_points")
    next_actions = payload.get("next_actions")
    data_limits = payload.get("data_limits")
    if not isinstance(review_points, list) or not isinstance(next_actions, list):
        raise CoachValidationError("AI coach lists are missing")
    if source_findings and not review_points:
        raise CoachValidationError("AI coach omitted all supplied findings")
    if not isinstance(data_limits, list) or not all(isinstance(item, str) for item in data_limits):
        raise CoachValidationError("AI coach data limits must be a string list")

    validated_points = []
    for index, point in enumerate(review_points[:4]):
        if not isinstance(point, dict):
            raise CoachValidationError(f"AI review point {index} must be an object")
        category = point.get("category")
        source = source_findings.get(category)
        if source is None:
            raise CoachValidationError(f"AI introduced unsupported category: {category}")
        evidence = _required_text(point.get("evidence"), f"review_points[{index}].evidence")
        action = _required_text(point.get("action"), f"review_points[{index}].action")
        if evidence != source.get("evidence"):
            raise CoachValidationError(f"AI rewrote evidence for category: {category}")
        if action != source.get("action"):
            raise CoachValidationError(f"AI rewrote action for category: {category}")
        why_it_matters = point.get("why_it_matters") or source.get("why_it_matters")
        if why_it_matters != source.get("why_it_matters"):
            raise CoachValidationError(f"AI rewrote impact for category: {category}")
        validated_points.append({
            "category": category,
            "title": point.get("title") or source.get("category_label") or category,
            "priority": source.get("priority"),
            "evidence": evidence,
            "why_it_matters": why_it_matters,
            "action": action,
            "system_check": source.get("replay_check"),
        })

    validated_actions = []
    for index, item in enumerate(next_actions[:5]):
        if not isinstance(item, dict):
            raise CoachValidationError(f"AI next action {index} must be an object")
        category = item.get("category")
        source = source_findings.get(category)
        if source is None:
            raise CoachValidationError(f"AI introduced unsupported action category: {category}")
        for field in ("action", "training_goal", "success_metric"):
            value = _required_text(item.get(field), f"next_actions[{index}].{field}")
            if value != source.get(field):
                raise CoachValidationError(f"AI rewrote {field} for category: {category}")
        validated_actions.append({
            "category": category,
            "title": item.get("title") or source.get("category_label") or category,
            "action": source.get("action"),
            "training_goal": source.get("training_goal"),
            "success_metric": source.get("success_metric"),
        })

    if source_findings and not validated_actions:
        raise CoachValidationError("AI coach omitted all measurable actions")
    return {
        "conclusion": conclusion,
        "review_points": validated_points,
        "next_actions": validated_actions,
        "data_limits": data_limits,
    }
