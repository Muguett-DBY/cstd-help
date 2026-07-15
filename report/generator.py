import os
import time
import shutil
import json
import hashlib
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from analysis.formula_engine import score_review_findings, select_formula_findings
from config import REPORT_DIR


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = BASE_DIR

AVAILABLE_SOURCE_LABELS = {
    "opendota_core_stats": "OpenDota比赛核心数据",
    "valve_replay_gem": "Valve原始回放解析",
    "final_item_slots": "最终装备栏",
    "ability_build": "技能加点",
    "stratz_player_detail": "STRATZ玩家详情",
    "draft_context": "十人阵容",
    "lane_timeline": "分钟补刀时间线",
    "gold_timeline": "分钟经济时间线",
    "opendota_parsed_logs": "OpenDota解析日志",
    "stratz_playback_cs": "STRATZ补刀事件",
    "purchase_timeline": "购买时间线",
    "opendota_event_logs": "OpenDota事件日志",
    "stratz_playback": "STRATZ回放事件",
    "opendota_teamfights": "OpenDota团战事件",
    "valve_replay_death_events": "Valve死亡事件",
    "fight_log": "个人击杀与助攻事件",
    "stratz_position_samples": "STRATZ位置采样",
    "opendota_death_positions": "OpenDota死亡坐标",
    "valve_replay_position_sample": "Valve实体位置采样",
    "valve_replay_all_player_positions": "Valve全员位置与生命状态",
    "vision_events": "视野事件",
    "opendota_objectives": "OpenDota地图目标事件",
    "stratz_building_objectives": "STRATZ建筑事件",
    "hero_benchmarks": "OpenDota同英雄百分位",
    "opendota_performance_context": "OpenDota表现汇总",
    "multi_source_performance_context": "多源表现汇总",
}


def generate_report(match_analysis, guidance, summary=None, output_dir=None, source_fetches=None):
    target_dir = os.fspath(output_dir or REPORT_DIR)
    os.makedirs(target_dir, exist_ok=True)

    static_src = os.path.join(BASE_DIR, "static")
    static_dst = os.path.join(target_dir, "static")
    stylesheet_path = os.path.join(static_src, "style.css")
    report_asset_version = "missing"
    if os.path.isfile(stylesheet_path):
        with open(stylesheet_path, "rb") as stylesheet_file:
            report_asset_version = hashlib.sha256(stylesheet_file.read()).hexdigest()[:12]
    if os.path.exists(static_src):
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("template.html")

    match_metadata = match_analysis.get("match_metadata", {})
    ended_at = match_metadata.get("ended_at")
    if ended_at:
        try:
            match_date = datetime.fromisoformat(ended_at.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            match_date = "结束时间未知"
    else:
        match_date = "结束时间未知"
    generated_now = datetime.now()
    generated_at = generated_now.strftime("%Y-%m-%d %H:%M:%S")
    report_metadata = dict(match_metadata)
    report_metadata["report_generated_at"] = generated_now.strftime("%Y-%m-%dT%H:%M:%S")
    report_metadata["source_fetches"] = dict(
        source_fetches or match_analysis.get("source_fetches") or {}
    )

    hero_name = match_analysis.get("hero_name", "Unknown")
    match_id = match_analysis.get("match_id", "N/A")
    is_win = match_analysis.get("is_win")
    duration_min = match_analysis.get("duration_min")
    duration_label = (
        f"{duration_min}分钟"
        if isinstance(duration_min, (int, float)) and not isinstance(duration_min, bool)
        else "未获取"
    )
    kda = match_analysis.get("kda", {})
    farm = match_analysis.get("farm", {})
    items = match_analysis.get("items", {})
    comparison = match_analysis.get("comparison", {})
    context = match_analysis.get("context", {})
    derived = match_analysis.get("derived", {})
    data_quality = dict(match_analysis.get("data_quality", {}))
    data_quality["available_labels"] = [
        AVAILABLE_SOURCE_LABELS.get(identifier, "其他已验证数据")
        for identifier in data_quality.get("available", [])
    ]
    death_position_source = next(
        (
            source.get("source")
            for source in data_quality.get("evidence_sources", [])
            if source.get("id") == "death_positions" and source.get("source")
        ),
        "公开数据源位置证据",
    )
    opendota_benchmarks = match_analysis.get("opendota_benchmarks", {})
    performance_context = match_analysis.get("performance_context", {})
    timeline = match_analysis.get("timeline", {})
    events = match_analysis.get("events", {})
    review_findings = match_analysis.get("review_findings", [])
    scored_findings = score_review_findings(match_analysis)
    priority_findings = select_formula_findings(match_analysis)
    priority_source_indices = {
        finding.get("source_index") for finding in priority_findings
    }
    secondary_findings = [
        finding for finding in scored_findings
        if finding.get("source_index") not in priority_source_indices
    ]
    role_profile = match_analysis.get("role_profile", {})
    issues = match_analysis.get("issues", [])
    suggestions = match_analysis.get("suggestions", [])
    d2pt = match_analysis.get("d2pt", None)

    html = template.render(
        hero_name=hero_name,
        match_id=match_id,
        match_date=match_date,
        is_win=is_win,
        duration_min=duration_min,
        duration_label=duration_label,
        kda=kda,
        farm=farm,
        items=items,
        comparison=comparison,
        context=context,
        derived=derived,
        data_quality=data_quality,
        death_position_source=death_position_source,
        opendota_benchmarks=opendota_benchmarks,
        performance_context=performance_context,
        timeline=timeline,
        events=events,
        review_findings=review_findings,
        scored_findings=scored_findings,
        priority_findings=priority_findings,
        secondary_findings=secondary_findings,
        role_profile=role_profile,
        issues=issues,
        suggestions=suggestions,
        d2pt=d2pt,
        guidance=guidance,
        summary=summary,
        generated_at=generated_at,
        report_asset_version=report_asset_version,
        report_metadata_json=json.dumps(report_metadata, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    safe_match_id = str(match_id).replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_hero = hero_name.replace(" ", "_").replace("'", "").replace("/", "_").replace("\\", "_")
    filename = f"{safe_hero}_{safe_match_id}_{generated_now.strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(target_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Report saved: {filepath}")
    return filepath
