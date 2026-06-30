import os
import time
import shutil
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = BASE_DIR
REPORT_DIR = r"C:\Users\12031\Desktop\REVIEW_REPORT"


def generate_report(match_analysis, ai_analysis, summary=None):
    os.makedirs(REPORT_DIR, exist_ok=True)

    static_src = os.path.join(BASE_DIR, "static")
    static_dst = os.path.join(REPORT_DIR, "static")
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
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    hero_name = match_analysis.get("hero_name", "Unknown")
    match_id = match_analysis.get("match_id", "N/A")
    is_win = match_analysis.get("is_win", False)
    duration_min = match_analysis.get("duration_min", 0)
    kda = match_analysis.get("kda", {})
    farm = match_analysis.get("farm", {})
    items = match_analysis.get("items", {})
    comparison = match_analysis.get("comparison", {})
    context = match_analysis.get("context", {})
    derived = match_analysis.get("derived", {})
    data_quality = match_analysis.get("data_quality", {})
    opendota_benchmarks = match_analysis.get("opendota_benchmarks", {})
    timeline = match_analysis.get("timeline", {})
    events = match_analysis.get("events", {})
    review_findings = match_analysis.get("review_findings", [])
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
        kda=kda,
        farm=farm,
        items=items,
        comparison=comparison,
        context=context,
        derived=derived,
        data_quality=data_quality,
        opendota_benchmarks=opendota_benchmarks,
        timeline=timeline,
        events=events,
        review_findings=review_findings,
        role_profile=role_profile,
        issues=issues,
        suggestions=suggestions,
        d2pt=d2pt,
        ai_analysis=ai_analysis,
        summary=summary,
        generated_at=generated_at,
        report_metadata_json=json.dumps(match_metadata, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    safe_match_id = str(match_id).replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_hero = hero_name.replace(" ", "_").replace("'", "").replace("/", "_").replace("\\", "_")
    filename = f"{safe_hero}_{safe_match_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(REPORT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Report saved: {filepath}")
    return filepath
