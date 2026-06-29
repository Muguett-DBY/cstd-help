import json
import requests
from config import ENABLE_FREEFORM_AI, OPENCODE_AI_BASE_URL, OPENCODE_AI_API_KEY, OPENCODE_AI_MODEL


SYSTEM_PROMPT = """你是一位专业的DOTA2电竞教练，专注于帮助玩家提升天梯段位。

你的职责：
1. 只基于用户提供的数据做复盘，不要编造对线过程、10分钟数据、装备时机、团战细节或职业选手均值
2. 先判断数据完整性：哪些结论有证据，哪些字段是公共数据源未提供
3. 从“最影响胜负的1-3个问题”入手，给出可执行的复盘动作
4. 对比D2PT数据时，只能使用提示词中明确提供的出装、加点、天赋和样本信息

你的风格：
- 直接、专业、有建设性
- 用中文回答
- 专注于最关键的提升点，不要泛泛而谈
- 给出具体的数字对比，但只能引用已提供的数字
- 按优先级排列建议，最重要的排前面
- 每个建议都要具体可执行
- 如果缺少时间线或事件数据，只能写“公共数据源未提供该字段”，不要假装已经看到
- 不要写推测、可能、大概、回放、回顾、人工或手动检查"""


AI_UNSAFE_TERMS = [
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
    "经济领先",
    "团队领先",
    "你方领先",
    "我方领先",
]


def analyze_with_ai(match_analysis, hero_name, is_win):
    if not ENABLE_FREEFORM_AI:
        return _generate_fallback_analysis(match_analysis, hero_name, is_win)
    if not OPENCODE_AI_API_KEY:
        return _generate_fallback_analysis(match_analysis, hero_name, is_win)

    prompt = _build_analysis_prompt(match_analysis, hero_name, is_win)

    try:
        headers = {
            "Authorization": f"Bearer {OPENCODE_AI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENCODE_AI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.25,
            "max_tokens": 3200,
        }
        resp = requests.post(
            f"{OPENCODE_AI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        if content:
            content = content.strip()
            if _is_ai_response_safe(content, match_analysis):
                return content
            print("  AI analyst output rejected: unsafe inference/manual-review language. Using deterministic fallback.")
    except Exception as e:
        print(f"  AI API error: {e}")

    return _generate_fallback_analysis(match_analysis, hero_name, is_win)


def _is_ai_response_safe(content, analysis):
    if not content or not content.strip():
        return False
    return not any(term in content for term in AI_UNSAFE_TERMS)


def _build_analysis_prompt(analysis, hero_name, is_win):
    farm = analysis.get("farm", {})
    kda = analysis.get("kda", {})
    derived = analysis.get("derived", {})
    context = analysis.get("context", {})
    data_quality = analysis.get("data_quality", {})
    items = analysis.get("items", {})
    timeline = analysis.get("timeline", {})
    events = analysis.get("events", {})
    review_findings = analysis.get("review_findings", [])
    role_profile = analysis.get("role_profile", {})
    result_text = "胜利" if is_win else "失败"

    prompt = f"""请分析以下DOTA2比赛数据并给出改进建议：

## 输出要求
- 先给出一句“本局最重要结论”
- 然后按 review_findings 的优先级列出最多3个复盘重点
- 每个重点必须包含：证据数字、为什么影响胜负、下一局怎么执行、训练目标、验收标准、系统已检查到什么
- 不得新增未在 review_findings 出现的问题
- 不要编造未提供的10分钟补刀、购买时间、对线细节、视野、团战站位或职业选手均值
- 对缺失数据只能写“公共数据源未提供该字段”，不能当作事实
- 不要写推测、可能、大概、回放、回顾、人工或手动检查

## 数据完整性
- 完整度评分: {data_quality.get('score', 0)}/100
- 可用数据: {', '.join(data_quality.get('available', [])) or '无'}
- 数据限制:
{_format_bullets(data_quality.get('limitations', []))}

## 比赛概况
- 英雄: {hero_name}
- 结果: {result_text}
- 时长: {analysis.get('duration_min', 0)}分钟
- 阵营: {context.get('side') or '未知'}
- 位置/分路: {context.get('role') or '未知'} / {context.get('lane') or '未知'}
- 队伍击杀: {context.get('team_kills') if context.get('team_kills') is not None else '未知'}
- 敌方击杀: {context.get('enemy_kills') if context.get('enemy_kills') is not None else '未知'}
- 敌方英雄: {', '.join(context.get('enemy_heroes', [])) or '缺失'}
- 角色画像: {role_profile.get('label', '未知')}；重点: {', '.join(role_profile.get('focus', [])) or '未知'}

## KDA数据
- 击杀/死亡/助攻: {kda.get('kills', 0)}/{kda.get('deaths', 0)}/{kda.get('assists', 0)}
- KDA比率: {kda.get('kda_ratio', 0)}
- 每10分钟死亡: {derived.get('deaths_per_10_min', 0)}
- 参战率: {derived.get('kill_participation_pct', '未知')}%

## 经济数据
- 正补/反补: {farm.get('last_hits', 0)}/{farm.get('denies', 0)}
- LH/min: {derived.get('lh_per_min', 0)}
- GPM: {farm.get('gpm', 0)}
- XPM: {farm.get('xpm', 0)}
- 英雄伤害: {farm.get('hero_damage', 0)}
- 伤害/分钟: {derived.get('hero_damage_per_min', 0)}
- 推塔伤害: {farm.get('tower_damage', 0)}
- 推塔伤害/分钟: {derived.get('tower_damage_per_min', 0)}
- 净财产: {farm.get('net_worth', 0)}

## 最终装备
{_format_item_details(items.get('final_item_details', []))}

## 时间线诊断
{_format_timeline(timeline)}

## 死亡/装备事件
{_format_events(events)}

## review_findings
{json.dumps(review_findings, ensure_ascii=False, indent=2)}

## 问题发现
"""
    for issue in analysis.get("issues", []):
        prompt += f"- [{issue.get('severity', 'info')}] {issue.get('message', '')}\n"

    prompt += "\n## 本地规则建议\n"
    for suggestion in analysis.get("suggestions", []):
        prompt += f"- [{suggestion.get('priority', 'info')}/{suggestion.get('category', 'general')}] {suggestion.get('message', '')}\n"

    d2pt = analysis.get("d2pt", {})
    if d2pt:
        prompt += f"\n## D2PT职业选手数据对比\n"
        prompt += f"- 职业选手胜率: {d2pt.get('winrate', 0)*100:.1f}%\n"
        prompt += f"- 样本量: {d2pt.get('matches', 0)}场\n"
        popular_items = d2pt.get("popular_items", [])
        if popular_items:
            prompt += "- 热门装备:\n"
            for item in popular_items[:8]:
                prompt += f"  - {item.get('name', '?')} ({item.get('pick_rate', 0)*100:.0f}%)\n"
        skill_build = d2pt.get("skill_build", [])
        if skill_build:
            prompt += "- 推荐加点前8级: "
            prompt += " -> ".join(f"Lv{s.get('level')}: {s.get('name', s.get('ability_id'))}" for s in skill_build[:8])
            prompt += "\n"
        talents = d2pt.get("talents", [])
        if talents:
            prompt += "- 天赋选择:\n"
            for t in talents[:4]:
                left = t.get("left", {})
                right = t.get("right", {})
                prompt += f"  - {t.get('level', '?')}级: 左={left.get('name', '?')}({left.get('pick_rate', 0)*100:.0f}%) vs 右={right.get('name', '?')}({right.get('pick_rate', 0)*100:.0f}%)\n"

    prompt += "\n请严格按 review_findings 和上述证据输出复盘，不要编造缺失数据。"
    return prompt


def _format_bullets(items):
    if not items:
        return "- 无明显限制"
    return "\n".join(f"- {item}" for item in items)


def _format_item_details(items):
    if not items:
        return "- 缺失"
    lines = []
    for item in items:
        lines.append(f"- {item.get('name', 'Unknown')} (ID {item.get('id')})")
    return "\n".join(lines)


def _format_timeline(timeline):
    if not timeline or not timeline.get("available"):
        return "- 缺少分钟级时间线"
    lines = [
        f"- 10分钟补刀: {timeline.get('ten_min_last_hits')}",
        f"- 20分钟补刀: {timeline.get('twenty_min_last_hits')}",
        f"- 20分钟平均GPM: {timeline.get('twenty_min_avg_gpm')}",
    ]
    for phase in timeline.get("phases", [])[:4]:
        lines.append(
            f"- {phase.get('label')}分钟: LH/min {phase.get('lh_per_min')}，"
            f"avg GPM {phase.get('avg_gpm')}，英雄伤害 {phase.get('hero_damage')}，推塔伤害 {phase.get('tower_damage')}"
        )
    for window in timeline.get("low_efficiency_windows", [])[:3]:
        lines.append(f"- {window.get('label')}: 平均补刀 {window.get('avg_lh')}/分钟")
    return "\n".join(lines)


def _format_events(events):
    if not events:
        return "- 缺少事件数据"
    lines = []
    purchases = events.get("purchases", [])
    deaths = events.get("deaths", [])
    if purchases:
        lines.append("- 购买事件: " + "；".join(
            f"{item.get('item_name')} {item.get('minute')}分钟" for item in purchases[:8]
        ))
    else:
        lines.append("- 购买事件: 公共数据源未提供 purchase_log")
    if events.get("death_coverage_label"):
        death_line = f"- 死亡覆盖: {events.get('death_coverage_label')}"
        if events.get("death_gap_note"):
            death_line += f"；{events.get('death_gap_note')}"
        lines.append(death_line)
    if deaths:
        death_parts = []
        for item in deaths[:8]:
            text = f"{item.get('minute')}分钟"
            if item.get("position_label"):
                text += f" {item.get('position_label')}"
            death_parts.append(text)
        lines.append("- 死亡事件: " + "；".join(death_parts))
    else:
        lines.append("- 死亡事件: 公共数据源未提供 death_log")
    return "\n".join(lines)


def _generate_fallback_analysis(analysis, hero_name, is_win):
    farm = analysis.get("farm", {})
    kda = analysis.get("kda", {})
    derived = analysis.get("derived", {})
    data_quality = analysis.get("data_quality", {})
    review_findings = analysis.get("review_findings", [])
    result_text = "胜利" if is_win else "失败"
    death_findings = [
        finding for finding in review_findings
        if finding.get("category") == "death_review"
    ]
    death_pressure = bool(death_findings) and (
        kda.get("deaths", 0) >= 5 or derived.get("deaths_per_10_min", 0) >= 1.0
    )

    lines = [f"{hero_name} 复盘分析（{result_text}）"]

    lines.append("")
    lines.append("本局最重要结论")
    if death_pressure:
        lines.append("当前最影响胜负的是死亡成本，优先使用已定位死亡分钟检查死亡前30秒的地图状态。")
    elif not is_win and analysis.get("duration_min", 0) >= 45 and farm.get("gpm", 0) >= 600:
        lines.append("高经济长局失利，优先复盘关键装备窗口是否转成地图目标，而不是继续泛化到补刀基本功。")
    elif kda.get("kda_ratio", 0) < 2 or derived.get("deaths_per_10_min", 0) >= 1.8:
        lines.append("当前最影响胜负的是死亡成本，优先使用已定位死亡分钟检查死亡前30秒的地图状态。")
    elif review_findings:
        top_finding = review_findings[0]
        top_label = top_finding.get("category_label") or top_finding.get("category") or "复盘重点"
        top_evidence = top_finding.get("evidence", "")
        evidence_text = f"：{top_evidence}" if top_evidence else ""
        lines.append(f"本局优先复盘{top_label}{evidence_text}")
    else:
        lines.append("核心指标没有暴露单点崩盘，复盘重点应放在关键装备后是否把经济转成地图目标。")

    lines.append("")
    lines.append(
        "核心证据："
        f"KDA {kda.get('kills', 0)}/{kda.get('deaths', 0)}/{kda.get('assists', 0)}，"
        f"GPM {farm.get('gpm', 0)}，LH/min {derived.get('lh_per_min', 0)}，"
        f"推塔伤害/分钟 {derived.get('tower_damage_per_min', 0)}，"
        f"每10分钟死亡 {derived.get('deaths_per_10_min', 0)}。"
    )
    if data_quality.get("score") is not None:
        lines.append(f"数据完整度：{data_quality.get('score', 0)}/100。")
    limitations = _coach_visible_limitations(data_quality)
    if limitations:
        lines.append("公共数据源缺口：" + "；".join(limitations[:3]) + "。")

    strengths = []
    if kda.get("kda_ratio", 0) >= 3 and not death_pressure:
        strengths.append(f"KDA表现优秀 ({kda.get('kda_ratio', 0)})，击杀/助攻收益高")
    if farm.get("gpm", 0) >= 500:
        strengths.append(f"GPM达到{farm.get('gpm', 0)}，经济效率不错")
    if farm.get("last_hits", 0) >= 50:
        strengths.append(f"补刀总量{farm.get('last_hits', 0)}，LH/min {derived.get('lh_per_min', 0)}")
    if strengths:
        lines.append("")
        lines.append("可以保留的习惯")
        for strength in strengths[:3]:
            lines.append(f"- {strength}")

    lines.append("")
    lines.append("下一局只盯这几件事")
    for idx, finding in enumerate(review_findings[:4], start=1):
        success_metric = finding.get("success_metric", "")
        metric_text = f" 验收：{success_metric}" if success_metric else ""
        lines.append(
            f"{idx}. {finding.get('category_label', finding.get('category', '复盘重点'))}: "
            f"{finding.get('action', '')}{metric_text}"
        )
    if not review_findings:
        for suggestion in analysis.get("suggestions", [])[:3]:
            lines.append(f"- {suggestion.get('priority', 'low')} / {suggestion.get('category', 'review')}: {suggestion.get('message', '')}")

    return "\n".join(lines)


def _coach_visible_limitations(data_quality):
    limitations = data_quality.get("limitations", []) or []
    available = set(data_quality.get("available", []) or [])
    if {"lane_timeline", "purchase_timeline"}.issubset(available):
        limitations = [
            item for item in limitations
            if not item.startswith("缺少Stratz玩家详情")
        ]
    return limitations
