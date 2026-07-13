from copy import deepcopy


REVIEW_SCHEMA_VERSION = 8
FORMULA_VERSION = 3


_PRIORITY_POINTS = {"high": 50, "medium": 30, "low": 15}
_DIMENSION_ORDER = {
    "death_objective": 0,
    "death_frequency": 1,
    "death_recovery": 2,
    "lane": 3,
    "economy": 4,
    "conversion": 5,
    "map": 6,
    "vision": 7,
    "other": 8,
}


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _clamp(value, lower=0.0, upper=100.0):
    return round(max(lower, min(upper, float(value))), 1)


def _mean(values):
    numbers = [float(value) for value in values if _number(value) is not None]
    return round(sum(numbers) / len(numbers), 1) if numbers else None


def _input(identifier, label, value, source, unit=""):
    return {
        "id": identifier,
        "label": label,
        "value": round(value, 2) if isinstance(value, float) else value,
        "unit": unit,
        "source": source,
    }


def _benchmark_map(analysis):
    return {
        item.get("id"): item
        for item in (analysis.get("opendota_benchmarks") or {}).get("metrics") or []
        if isinstance(item, dict) and item.get("id")
    }


def _benchmark_percentile(benchmarks, metric_id):
    item = benchmarks.get(metric_id) or {}
    value = _number(item.get("percentile"))
    if value is None:
        pct = _number(item.get("pct"))
        value = pct * 100 if pct is not None else None
    return _clamp(value) if value is not None else None


def _weighted_score(components):
    available = [item for item in components if _number(item.get("value")) is not None]
    total_weight = sum(float(item["weight"]) for item in available)
    if not available or total_weight <= 0:
        return None, ""
    score = sum(float(item["value"]) * float(item["weight"]) for item in available) / total_weight
    equation = " + ".join(
        f"{item['weight']:g}x{item['label']}({float(item['value']):.1f})"
        for item in available
    )
    return _clamp(score), f"({equation}) / {total_weight:g}"


def _is_meaningful_resource_drop(window):
    if window.get("has_resource_drop") or window.get("resource_drop"):
        return True
    lh_delta = _number(window.get("lh_per_min_delta"))
    gpm_delta = _number(window.get("avg_gpm_delta"))
    return bool(
        (lh_delta is not None and lh_delta <= -2.0)
        or (gpm_delta is not None and gpm_delta <= -150.0)
    )


def _scorecard(identifier, label, score, equation, inputs, weight, threshold, interpretation):
    return {
        "id": identifier,
        "label": label,
        "score": _clamp(score),
        "weight": weight,
        "formula_id": f"dota_review_v{FORMULA_VERSION}.{identifier}",
        "equation": equation,
        "inputs": inputs,
        "threshold": threshold,
        "status": "strong" if score >= 75 else "attention" if score < 50 else "normal",
        "interpretation": interpretation,
    }


def _lane_scorecard(analysis):
    role_id = (analysis.get("role_profile") or {}).get("id") or "unknown"
    performance = analysis.get("performance_context") or {}
    timeline = analysis.get("timeline") or {}
    lane_efficiency = _number(performance.get("lane_efficiency_pct"))
    ten_lh = _number(timeline.get("ten_min_last_hits"))
    lh_targets = {"pos1": 50, "pos2": 45, "pos3": 40}
    components = []
    inputs = []
    if lane_efficiency is not None:
        components.append({"label": "对线效率", "value": lane_efficiency, "weight": 0.65})
        inputs.append(_input("lane_efficiency_pct", "对线效率", lane_efficiency, "OpenDota", "%"))
    target = lh_targets.get(role_id)
    if ten_lh is not None and target:
        lh_score = _clamp((ten_lh / target) * 100)
        components.append({"label": "10分钟补刀达成率", "value": lh_score, "weight": 0.35})
        inputs.append(_input("ten_min_last_hits", "10分钟补刀", ten_lh, "OpenDota/STRATZ", "个"))
        inputs.append(_input("ten_min_lh_training_target", "位置训练阈值", target, "系统规则", "个"))
    score, equation = _weighted_score(components)
    if score is None:
        return None
    return _scorecard(
        "laning",
        "对线资源",
        score,
        equation,
        inputs,
        0.22,
        "75分以上为稳定；阈值是训练规则，不是职业均值",
        "衡量对线效率与前10分钟可记录补刀，不解释离线原因。",
    )


def _economy_scorecard(analysis, benchmarks):
    metric_labels = {
        "gold_per_min": "GPM百分位",
        "xp_per_min": "XPM百分位",
        "last_hits_per_min": "LH/min百分位",
    }
    components = []
    inputs = []
    for metric_id, label in metric_labels.items():
        percentile = _benchmark_percentile(benchmarks, metric_id)
        if percentile is None:
            continue
        components.append({"label": label, "value": percentile, "weight": 1})
        inputs.append(_input(metric_id, label, percentile, "OpenDota同英雄样本", "百分位"))
    score, equation = _weighted_score(components)
    if score is None:
        return None
    return _scorecard(
        "economy",
        "经济效率",
        score,
        equation,
        inputs,
        0.24,
        "50为同英雄样本中位，70以上为本局强项",
        "只比较OpenDota返回的同英雄样本百分位。",
    )


def _survival_scorecard(analysis):
    performance = analysis.get("performance_context") or {}
    timeline = analysis.get("timeline") or {}
    events = analysis.get("events") or {}
    dead_share = _number(performance.get("dead_time_share_pct"))
    if dead_share is None:
        return None
    objective_losses = len({
        item.get("death_time", item.get("death_minute"))
        for item in events.get("death_objective_windows") or []
        if item.get("death_time") is not None or item.get("death_minute") is not None
    })
    resource_drops = sum(
        1 for item in timeline.get("death_resource_deltas") or []
        if _is_meaningful_resource_drop(item)
    )
    penalty = dead_share * 3 + objective_losses * 12 + resource_drops * 8
    score = _clamp(100 - min(100, penalty))
    inputs = [
        _input("dead_time_share_pct", "死亡占时", dead_share, "OpenDota", "%"),
        _input("death_objective_losses", "死亡后90秒目标损失", objective_losses, "死亡+目标事件", "次"),
        _input("death_resource_drops", "死亡后资源下降窗口", resource_drops, "分钟数组+死亡事件", "个"),
    ]
    return _scorecard(
        "survival",
        "生存成本",
        score,
        f"100 - min(100, {dead_share:g}x3 + {objective_losses}x12 + {resource_drops}x8)",
        inputs,
        0.22,
        "75分以上表示死亡占时与后续可记录损失受控",
        "惩罚只来自死亡占时、目标损失和资源下降窗口。",
    )


def _conversion_scorecard(analysis, benchmarks):
    performance = analysis.get("performance_context") or {}
    events = analysis.get("events") or {}
    components = []
    inputs = []
    participation = _number(performance.get("teamfight_participation_pct"))
    if participation is not None:
        components.append({"label": "参战率", "value": participation, "weight": 0.45})
        inputs.append(_input("teamfight_participation_pct", "参战率", participation, "OpenDota", "%"))
    tower_percentile = _benchmark_percentile(benchmarks, "tower_damage")
    if tower_percentile is not None:
        components.append({"label": "建筑伤害百分位", "value": tower_percentile, "weight": 0.35})
        inputs.append(_input("tower_damage", "建筑伤害", tower_percentile, "OpenDota同英雄样本", "百分位"))
    windows = events.get("post_item_windows") or []
    if windows:
        converted = sum(
            1 for item in windows
            if item.get("classification") not in {"low_conversion", "low_farm"}
            and not item.get("low_conversion")
            and not item.get("low_farm")
        )
        conversion_rate = round(converted / len(windows) * 100, 1)
        components.append({"label": "装备后窗口转化率", "value": conversion_rate, "weight": 0.2})
        inputs.append(_input("post_item_conversion_rate", "装备后窗口转化", conversion_rate, "购买+参战+推塔事件", "%"))
    score, equation = _weighted_score(components)
    if score is None:
        return None
    return _scorecard(
        "conversion",
        "地图转化",
        score,
        equation,
        inputs,
        0.18,
        "65分以上表示本局经济较稳定地转成参战或建筑压力",
        "组合参战、建筑伤害和关键装备后可记录事件。",
    )


def _role_scorecard(analysis, benchmarks):
    role_id = (analysis.get("role_profile") or {}).get("id") or "unknown"
    performance = analysis.get("performance_context") or {}
    extended = analysis.get("extended_metrics") or {}
    events = analysis.get("events") or {}
    duration = max(_number(analysis.get("duration_min")) or 0, 1)
    components = []
    inputs = []

    if role_id == "support":
        participation = _number(performance.get("teamfight_participation_pct"))
        if participation is not None:
            components.append({"label": "参战率", "value": participation, "weight": 0.45})
            inputs.append(_input("teamfight_participation_pct", "参战率", participation, "OpenDota", "%"))
        vision_count = len(events.get("observer_wards") or []) + len(events.get("sentry_wards") or [])
        if events.get("has_vision_log"):
            vision_per_ten = vision_count / duration * 10
            vision_score = _clamp(vision_per_ten / 2 * 100)
            components.append({"label": "每10分钟视野动作达成率", "value": vision_score, "weight": 0.55})
            inputs.append(_input("vision_events_per_10", "每10分钟视野动作", round(vision_per_ten, 2), "OpenDota视野日志", "次"))
            inputs.append(_input("vision_training_target", "训练阈值", 2, "系统规则", "次/10分钟"))
    else:
        for metric_id, label, weight in (
            ("hero_damage_per_min", "英雄伤害百分位", 0.55),
            ("tower_damage", "建筑伤害百分位", 0.45),
        ):
            percentile = _benchmark_percentile(benchmarks, metric_id)
            if percentile is not None:
                components.append({"label": label, "value": percentile, "weight": weight})
                inputs.append(_input(metric_id, label, percentile, "OpenDota同英雄样本", "百分位"))

    score, equation = _weighted_score(components)
    if score is None:
        return None
    label = "辅助执行" if role_id == "support" else "输出与推进"
    return _scorecard(
        "role_execution",
        label,
        score,
        equation,
        inputs,
        0.14,
        "70分以上为本局该位置的稳定执行项",
        "按已识别位置选择真实指标，不跨位置套用同一阈值。",
    )


def build_formula_diagnostics(analysis):
    analysis = analysis or {}
    benchmarks = _benchmark_map(analysis)
    builders = (
        _lane_scorecard(analysis),
        _economy_scorecard(analysis, benchmarks),
        _survival_scorecard(analysis),
        _conversion_scorecard(analysis, benchmarks),
        _role_scorecard(analysis, benchmarks),
    )
    scorecards = [card for card in builders if card is not None]
    present_ids = {card["id"] for card in scorecards}
    expected = (
        ("laning", "对线资源"),
        ("economy", "经济效率"),
        ("survival", "生存成本"),
        ("conversion", "地图转化"),
        ("role_execution", "位置执行"),
    )
    unscored = [
        {"id": identifier, "label": label, "reason": "所需真实字段未返回，未计算也未估算"}
        for identifier, label in expected
        if identifier not in present_ids
    ]
    total_weight = sum(card["weight"] for card in scorecards)
    overall = (
        _clamp(sum(card["score"] * card["weight"] for card in scorecards) / total_weight)
        if total_weight else None
    )
    overall_terms = " + ".join(
        f"{card['weight']:g}x{card['label']}({card['score']:.1f})"
        for card in scorecards
    )
    overall_equation = f"({overall_terms}) / {total_weight:g}" if total_weight else ""
    overall_inputs = [
        {
            "id": card["id"],
            "label": card["label"],
            "value": card["score"],
            "unit": "分",
            "weight": card["weight"],
            "source": card["formula_id"],
        }
        for card in scorecards
    ]
    return {
        "formula_version": FORMULA_VERSION,
        "overall_score": overall,
        "overall_equation": overall_equation,
        "overall_inputs": overall_inputs,
        "scorecards": scorecards,
        "unscored_dimensions": unscored,
    }


def _finding_dimension(category):
    category = str(category or "")
    if category == "death_objective_window":
        return "death_objective"
    if category == "death_review":
        return "death_frequency"
    if category.startswith("death_"):
        return "death_recovery"
    if category == "lane_farm":
        return "lane"
    if category in {"resource_continuity", "hero_benchmark_gap"}:
        return "economy"
    if category == "item_timing":
        return "conversion"
    if category in {"map_impact", "closing"}:
        return "map"
    if category == "support_vision":
        return "vision"
    return "other"


def _finding_magnitude(category, analysis):
    timeline = analysis.get("timeline") or {}
    events = analysis.get("events") or {}
    performance = analysis.get("performance_context") or {}
    if category == "death_objective_window":
        windows = events.get("death_objective_windows") or []
        unique_deaths = len({
            item.get("death_time", item.get("death_minute"))
            for item in windows
            if item.get("death_time") is not None or item.get("death_minute") is not None
        })
        drill = events.get("death_objective_drill") or {}
        severity = _number(drill.get("focus_severity_points"))
        if severity is None:
            severity = max(
                ({"ancient": 14, "barracks": 10, "roshan": 8, "aegis": 8, "tower": 6}.get(
                    item.get("objective_kind"), 4
                ) for item in windows),
                default=0,
            )
            severity_label = "最高目标级别权重"
            severity_source = "确定性目标权重"
            magnitude_equation = "min(35,6x关联死亡数+最高目标级别权重)"
        else:
            severity_label = "最高同一死亡窗口累计目标权重"
            severity_source = "目标窗口聚合规则"
            magnitude_equation = "min(35,6x关联死亡数+累计目标权重)"
        impact = min(35, unique_deaths * 6 + severity)
        return impact, [
            _input("linked_objective_deaths", "关联目标损失的死亡", unique_deaths, "死亡+目标事件", "次"),
            _input("objective_severity_weight", severity_label, severity, severity_source, "分"),
        ], magnitude_equation
    if category in {"death_recovery", "death_resource_delta", "death_resource_overlap"}:
        count = sum(
            1 for item in timeline.get("death_resource_deltas") or []
            if _is_meaningful_resource_drop(item)
        )
        return min(35, count * 8), [
            _input("death_resource_drop_windows", "死亡资源下降窗口", count, "分钟数组+死亡事件", "个"),
        ], "8x死亡资源下降窗口数"
    if category == "death_review":
        dead_share = _number(performance.get("dead_time_share_pct")) or 0
        count = len(events.get("deaths") or [])
        magnitude = min(35, dead_share * 0.8 + count * 1.8)
        return magnitude, [
            _input("dead_time_share_pct", "死亡占时", dead_share, "OpenDota", "%"),
            _input("timed_death_count", "有时间戳死亡", count, "死亡事件", "次"),
        ], "min(35,0.8x死亡占时%+1.8x死亡数)"
    if category == "death_position_pattern":
        count = len(events.get("death_position_clusters") or [])
        return min(35, count * 7), [
            _input("death_position_clusters", "重复死亡坐标簇", count, "死亡坐标事件", "个"),
        ], "7x重复死亡坐标簇数"
    if category == "item_timing":
        windows = events.get("post_item_windows") or []
        low_count = sum(
            1 for item in windows
            if item.get("classification") in {"low_conversion", "low_farm"}
            or item.get("low_conversion") or item.get("low_farm")
        )
        return min(35, max(1, low_count) * 10), [
            _input("low_conversion_item_windows", "低转化装备窗口", low_count, "购买+团战+建筑事件", "个"),
        ], "10xmax(1,低转化窗口数)"
    if category == "lane_farm":
        lane = _number(performance.get("lane_efficiency_pct"))
        low_count = len([
            item for item in timeline.get("low_efficiency_windows") or []
            if (item.get("start_minute") or 0) < 10
        ])
        gap = max(0, 70 - lane) if lane is not None else 0
        return min(35, gap * 0.8 + low_count * 6), [
            _input("lane_efficiency_gap", "距70%训练阈值", round(gap, 1), "OpenDota+系统规则", "个百分点"),
            _input("early_low_efficiency_windows", "前10分钟低效窗口", low_count, "分钟数组", "个"),
        ], "0.8x(70-对线效率)+6x前10分钟低效窗口"
    if category == "resource_continuity":
        windows = timeline.get("low_efficiency_windows") or []
        death_minutes = [
            _number(item.get("minute"))
            for item in events.get("deaths") or []
            if _number(item.get("minute")) is not None
        ]
        uncovered = [
            item for item in windows
            if not any(
                _number(item.get("start_minute")) <= minute <= _number(item.get("end_minute"))
                for minute in death_minutes
                if _number(item.get("start_minute")) is not None
                and _number(item.get("end_minute")) is not None
            )
        ]
        count = len(uncovered)
        return min(35, count * 7), [
            _input("non_death_low_efficiency_windows", "非死亡重叠低效率窗口", count, "分钟数组+死亡事件", "个"),
        ], "7x非死亡重叠低效率窗口数"
    if category == "map_impact":
        participation = _number(performance.get("teamfight_participation_pct"))
        gap = max(0, 40 - participation) if participation is not None else 0
        return min(35, gap), [
            _input("teamfight_participation_gap", "距40%参战训练阈值", round(gap, 1), "OpenDota+系统规则", "个百分点"),
        ], "max(0,40-参战率)"
    return 5, [
        _input("verified_rule_trigger", "已触发可验证规则", 1, "确定性发现规则", "条"),
    ], "固定可验证问题权重"


def actionable_findings(analysis):
    findings = []
    for item in (analysis or {}).get("review_findings") or []:
        if not isinstance(item, dict):
            continue
        success_metric = str(item.get("success_metric") or "")
        action = str(item.get("action") or "")
        training_goal = str(item.get("training_goal") or "")
        category = item.get("category")
        if success_metric.startswith("数据验收："):
            continue
        if any(
            marker in action or marker in training_goal
            for marker in ("系统会继续请求", "后续抓取", "先保证系统拿到")
        ):
            continue
        if category == "death_position_pattern":
            continue
        if category == "resource_continuity":
            windows = (analysis.get("timeline") or {}).get("low_efficiency_windows") or []
            deaths = (analysis.get("events") or {}).get("deaths") or []
            death_minutes = [
                _number(death.get("minute"))
                for death in deaths
                if _number(death.get("minute")) is not None
            ]
            if windows and all(
                any(
                    _number(window.get("start_minute")) <= minute <= _number(window.get("end_minute"))
                    for minute in death_minutes
                    if _number(window.get("start_minute")) is not None
                    and _number(window.get("end_minute")) is not None
                )
                for window in windows
            ):
                continue
        findings.append(item)
    return findings


def score_review_findings(analysis):
    quality = _number((analysis.get("data_quality") or {}).get("score"))
    confidence_points = round((quality or 0) * 0.1, 1)
    scored = []
    for index, source in enumerate(actionable_findings(analysis)):
        if not isinstance(source, dict):
            continue
        finding = deepcopy(source)
        category = finding.get("category") or "other"
        priority_points = _PRIORITY_POINTS.get(finding.get("priority"), 20)
        magnitude_points, magnitude_inputs, magnitude_equation = _finding_magnitude(category, analysis)
        formula_score = _clamp(priority_points + magnitude_points + confidence_points)
        finding.update({
            "formula_score": formula_score,
            "formula_id": f"dota_review_v{FORMULA_VERSION}.finding_priority",
            "formula": (
                f"min(100, 优先级{priority_points} + "
                f"幅度{magnitude_points:g}[{magnitude_equation}] + "
                f"证据完整度{confidence_points:g})"
            ),
            "formula_inputs": [
                _input("priority_points", "规则优先级", priority_points, "确定性发现规则", "分"),
                *magnitude_inputs,
                _input("impact_points", f"影响幅度：{magnitude_equation}", magnitude_points, "确定性幅度公式", "分"),
                _input("evidence_completeness", "证据完整度", quality or 0, "字段覆盖账本", "%"),
            ],
            "dimension": _finding_dimension(category),
            "source_index": index,
        })
        scored.append(finding)
    scored.sort(key=lambda item: (
        -item["formula_score"],
        _DIMENSION_ORDER.get(item["dimension"], 99),
        item["source_index"],
    ))
    return scored


def select_formula_findings(analysis, limit=4):
    scored = score_review_findings(analysis)
    selected = []
    dimensions = set()
    for finding in scored:
        if finding["dimension"] in dimensions:
            continue
        selected.append(finding)
        dimensions.add(finding["dimension"])
        if len(selected) >= limit:
            break
    return selected


def build_formula_review(analysis):
    diagnostics = build_formula_diagnostics(analysis)
    findings = select_formula_findings(analysis)
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
            "formula_score": finding.get("formula_score"),
            "formula_id": finding.get("formula_id"),
            "formula": finding.get("formula"),
            "formula_inputs": finding.get("formula_inputs"),
        })
        next_actions.append({
            "category": finding.get("category"),
            "title": finding.get("category_label") or finding.get("category"),
            "priority": finding.get("priority"),
            "action": finding.get("action"),
            "training_goal": finding.get("training_goal"),
            "success_metric": finding.get("success_metric"),
            "formula_score": finding.get("formula_score"),
        })

    if findings:
        top = findings[0]
        label = top.get("category_label") or top.get("category") or "本局重点"
        conclusion = f"{label}以{top['formula_score']:.1f}分列为首要训练项：{top.get('evidence') or '已有比赛证据'}"
    else:
        conclusion = "现有真实字段没有触发问题规则，本局保留分项得分与事实数据。"

    return {
        "analysis_mode": "deterministic_formula",
        "formula_version": FORMULA_VERSION,
        "overall_score": diagnostics["overall_score"],
        "overall_equation": diagnostics["overall_equation"],
        "overall_inputs": diagnostics["overall_inputs"],
        "scorecards": diagnostics["scorecards"],
        "unscored_dimensions": diagnostics["unscored_dimensions"],
        "conclusion": conclusion,
        "review_points": review_points,
        "next_actions": next_actions,
        "data_limits": list((analysis.get("data_quality") or {}).get("limitations") or []),
    }
