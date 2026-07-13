import {
    apiFetch,
    attachImageFallbacks,
    escapeHtml,
    formatDuration,
    formatLocalTime,
    getMatchId,
    heroImageUrl,
    itemImageUrl,
    laneRoleLabel,
    minuteLabel,
    numberLabel,
    refreshIcons,
    resultMeta,
} from "/static/shared.js?v=60b55d2f55b2";

const matchId = getMatchId();
const pageStatus = document.querySelector("[data-page-status]");
const analyzeButton = document.querySelector("[data-generate-review]");
const reviewOutput = document.querySelector("[data-review-output]");
const heroHeading = document.querySelector("[data-hero-heading]");
const state = { detail: null, reviewStatus: null, review: null };
const MAX_REVIEW_POLL_ATTEMPTS = 60;

function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function setPageStatus(message, tone = "neutral") {
    pageStatus.textContent = message;
    pageStatus.dataset.tone = tone;
}

function setAnalysisBusy(busy) {
    analyzeButton.disabled = busy || !state.detail;
    analyzeButton.setAttribute("aria-busy", String(busy));
    analyzeButton.querySelector("svg")?.classList.toggle("pulse", busy);
    if (busy) analyzeButton.querySelector("span").textContent = "正在计算公式…";
}

function metric(label, value, emphasis = false) {
    return `<div class="fact-item ${emphasis ? "emphasis" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function participantRow(participant) {
    const hero = participant.hero || {};
    const image = heroImageUrl(hero);
    const kda = participant.kda || {};
    return `
        <div class="participant ${participant.is_self ? "is-self" : ""}">
            <span class="participant-image ${image ? "" : "image-missing"}">
                ${image ? `<img src="${image}" width="72" height="41" alt="" loading="lazy" data-image-fallback>` : ""}
            </span>
            <span class="participant-name"><strong>${escapeHtml(hero.name || "未知英雄")}</strong><small>${participant.is_self ? "你" : escapeHtml(participant.personaname || laneRoleLabel(participant.lane_role))}</small></span>
            <span class="participant-kda">${Number(kda.kills) || 0} / <b>${Number(kda.deaths) || 0}</b> / ${Number(kda.assists) || 0}</span>
            <span class="participant-stats"><small>${numberLabel(participant.last_hits)} LH</small><small>${numberLabel(participant.gold_per_min)} / ${numberLabel(participant.xp_per_min)}</small><small>${numberLabel(participant.hero_damage)} 伤害</small></span>
            <span class="participant-net">${numberLabel(participant.net_worth)}</span>
        </div>`;
}

function renderParticipants(participants) {
    const target = document.querySelector("[data-participants]");
    const radiant = (participants || []).filter((player) => player.side === "radiant");
    const dire = (participants || []).filter((player) => player.side === "dire");
    const team = (name, side, players) => `
        <section class="team-lineup ${side}" aria-label="${name}">
            <header><span>${name}</span><small>${players.length} 名英雄</small></header>
            <div>${players.map(participantRow).join("") || '<p class="muted-copy">阵容数据未返回</p>'}</div>
        </section>`;
    target.innerHTML = team("天辉", "radiant", radiant) + team("夜魇", "dire", dire);
    attachImageFallbacks(target);
}

function renderFinalItems(items) {
    const target = document.querySelector("[data-final-items]");
    if (!items?.length) {
        target.innerHTML = '<span class="muted-copy">本局最终装备数据未返回</span>';
        return;
    }
    target.innerHTML = items.map((item) => {
        const image = itemImageUrl(item);
        return `
            <div class="item-slot" title="${escapeHtml(item.name)}">
                <span class="item-image ${image ? "" : "image-missing"}">
                    ${image ? `<img src="${image}" width="64" height="47" alt="" loading="lazy" data-image-fallback>` : ""}
                </span>
                <span><strong>${escapeHtml(item.name)}</strong><small>${item.cost ? `${numberLabel(item.cost)} 金` : "最终装备"}</small></span>
            </div>`;
    }).join("");
    attachImageFallbacks(target);
}

function renderFactualDetail(payload) {
    state.detail = payload;
    const summary = payload.summary || {};
    const player = payload.player || {};
    const participants = payload.participants || [];
    const self = participants.find((participant) => participant.is_self) || {};
    const hero = summary.hero || self.hero || {};
    const heroName = hero.name || "未知英雄";
    const result = resultMeta(summary.is_win);
    const image = heroImageUrl(hero);

    document.title = `${heroName}｜天梯复盘`;
    heroHeading.textContent = `${heroName} 复盘`;
    document.querySelector("[data-hero-portrait]").innerHTML = image
        ? `<img src="${image}" width="224" height="128" alt="${escapeHtml(heroName)}" data-image-fallback>`
        : '<span class="portrait-placeholder"></span>';
    const badge = document.querySelector("[data-result-badge]");
    badge.className = `result-badge ${result.key}`;
    badge.textContent = result.label;
    document.querySelector("[data-match-id]").textContent = `比赛 #${payload.match_id}`;
    const endedAt = document.querySelector("[data-ended-at]");
    endedAt.dateTime = summary.ended_at || "";
    endedAt.textContent = formatLocalTime(summary.ended_at, true);

    const detail = payload.detail || {};
    document.querySelector("[data-score]").textContent = `${Number(detail.radiant_score) || 0} : ${Number(detail.dire_score) || 0}`;
    document.querySelector("[data-fact-strip]").innerHTML = [
        metric("K / D / A", `${Number(player.kills) || 0} / ${Number(player.deaths) || 0} / ${Number(player.assists) || 0}`, true),
        metric("GPM", numberLabel(player.gold_per_min)),
        metric("XPM", numberLabel(player.xp_per_min)),
        metric("补刀 / 反补", `${numberLabel(player.last_hits)} / ${numberLabel(player.denies)}`),
        metric("英雄伤害", numberLabel(player.hero_damage)),
        metric("建筑伤害", numberLabel(player.tower_damage)),
        metric("净资产", numberLabel(player.net_worth)),
        metric("操作 / 分", numberLabel(player.actions_per_min)),
        metric("控制时长", `${Number(player.stuns || 0).toFixed(1)} 秒`),
        metric("视野放置", `${numberLabel(player.obs_placed)} / ${numberLabel(player.sen_placed)}`),
        metric("堆野 / 符文", `${numberLabel(player.camps_stacked)} / ${numberLabel(player.rune_pickups)}`),
        metric("时长", formatDuration(player.duration || summary.duration_seconds)),
    ].join("");
    renderParticipants(participants);
    renderFinalItems(self.items || []);
    attachImageFallbacks(document);
    analyzeButton.disabled = false;
    setAnalysisButtonLabel();
    setPageStatus(`${result.label} · ${heroName} · 比赛事实已加载`, "success");
    refreshIcons();
}

function setAnalysisButtonLabel() {
    const label = analyzeButton.querySelector("span");
    if (state.review) label.textContent = "复盘已打开";
    else if (state.reviewStatus?.exists) label.textContent = "打开已生成复盘";
    else label.textContent = "生成数据复盘";
}

function renderActions(actions) {
    const target = document.querySelector("[data-actions]");
    target.innerHTML = (actions || []).map((action, index) => `
        <article class="action-item">
            <span class="action-index">${String(index + 1).padStart(2, "0")}</span>
            <div><h4>${escapeHtml(action.title || action.category || "训练项")}</h4><p>${escapeHtml(action.action || "")}</p>
                <dl><div><dt>训练目标</dt><dd>${escapeHtml(action.training_goal || "")}</dd></div><div><dt>验收</dt><dd>${escapeHtml(action.success_metric || "")}</dd></div></dl>
            </div>
        </article>`).join("") || '<p class="muted-copy">本局没有形成可发布的行动项。</p>';
}

function formulaInputRow(input) {
    const value = input?.value === null || input?.value === undefined ? "—" : input.value;
    return `<li><span>${escapeHtml(input?.label || input?.id || "输入")}</span><strong>${escapeHtml(`${value}${input?.unit || ""}`)}</strong><small>${escapeHtml(input?.source || "来源未记录")}</small></li>`;
}

function renderFormulaScores(guidance) {
    const target = document.querySelector("[data-formula-scores]");
    const scorecards = guidance?.scorecards || [];
    const unscored = guidance?.unscored_dimensions || [];
    const overall = Number(guidance?.overall_score);
    const overallEquation = guidance?.overall_equation || "";
    const cards = scorecards.map((card) => `
        <article class="formula-card status-${escapeHtml(card.status || "normal")}">
            <header><div><span>${escapeHtml(card.formula_id || "确定性公式")}</span><h4>${escapeHtml(card.label || card.id)}</h4></div><strong>${numberLabel(card.score)}<small>/100</small></strong></header>
            <p>${escapeHtml(card.interpretation || "")}</p>
            <code>${escapeHtml(card.equation || "")}</code>
            <ul>${(card.inputs || []).map(formulaInputRow).join("")}</ul>
            <footer><strong>分项权重 ${Number.isFinite(Number(card.weight)) ? `${numberLabel(Number(card.weight) * 100)}%` : "—"}</strong><span>${escapeHtml(card.threshold || "")}</span></footer>
        </article>`).join("");
    const unscoredRows = unscored.map((item) => `<li><strong>${escapeHtml(item.label || item.id)}</strong><span>${escapeHtml(item.reason || "未计算")}</span></li>`).join("");
    target.innerHTML = `
        <div class="formula-overall"><span>综合执行分</span><strong>${Number.isFinite(overall) ? numberLabel(overall) : "—"}<small>/100</small></strong><p>只对已返回的真实字段按分项权重归一化。</p>${overallEquation ? `<code>${escapeHtml(overallEquation)}</code>` : ""}</div>
        <div class="formula-grid">${cards || '<p class="muted-copy">当前没有足够真实字段计算分项。</p>'}</div>
        ${unscoredRows ? `<details class="unscored-list"><summary>未计算分项 ${unscored.length}</summary><ul>${unscoredRows}</ul></details>` : ""}`;
}

function benchmarkRawLabel(item) {
    const value = Number(item?.raw);
    if (!Number.isFinite(value)) return "—";
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function renderPerformanceContext(analysis) {
    const target = document.querySelector("[data-performance-context]");
    const role = analysis.role_profile || {};
    const performance = analysis.performance_context || {};
    const benchmarks = analysis.opendota_benchmarks || {};
    const focus = (role.focus || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const performanceRows = (performance.metrics || []).map((item) => `
        <div class="context-metric status-${escapeHtml(item.status || "normal")}">
            <dt>${escapeHtml(item.label || "指标")}</dt>
            <dd><strong>${escapeHtml(item.value_label || "—")}</strong><small>${escapeHtml(item.detail || "")}</small></dd>
        </div>`).join("");
    const benchmarkRows = (benchmarks.metrics || []).map((item) => `
        <div class="benchmark-row status-${escapeHtml(item.status || "normal")}">
            <span>${escapeHtml(item.label || item.id || "指标")}</span>
            <strong>${escapeHtml(item.percentile_label || "—")}</strong>
            <small>本局 ${benchmarkRawLabel(item)}</small>
        </div>`).join("");
    const qualityScore = Number(analysis.data_quality?.score);
    target.innerHTML = `
        <div class="role-context-strip">
            <div><span>本局位置</span><strong>${escapeHtml(role.label || "位置未识别")}</strong></div>
            <div><span>证据完整度</span><strong>${Number.isFinite(qualityScore) ? `${qualityScore}/100` : "—"}</strong></div>
            <div><span>分析重点</span><ul>${focus || "<li>按事件证据排序</li>"}</ul></div>
        </div>
        <div class="performance-context-grid">
            <section><h4>本局执行指标</h4><dl>${performanceRows || '<p class="muted-copy">公共数据源未返回执行汇总。</p>'}</dl></section>
            <section><h4>同英雄样本位置</h4><div class="benchmark-list">${benchmarkRows || '<p class="muted-copy">公共数据源未返回同英雄百分位。</p>'}</div></section>
        </div>`;
}

function extendedMetric(label, value, suffix = "") {
    const normalized = value === null || value === undefined
        ? "—"
        : typeof value === "string" ? `${value}${suffix}` : `${numberLabel(value)}${suffix}`;
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(normalized)}</dd></div>`;
}

function usageRows(items) {
    return (items || []).slice(0, 6).map((item) => `<li><span>${escapeHtml(item.name)}</span><strong>${numberLabel(item.count)} 次</strong></li>`).join("");
}

function renderExtendedMetrics(extended) {
    const target = document.querySelector("[data-extended-metrics]");
    if (!extended?.available) {
        target.innerHTML = '<p class="muted-copy">扩展字段未返回。</p>';
        return;
    }
    const combat = extended.combat || {};
    const economy = extended.economy || {};
    const vision = extended.vision || {};
    const activity = extended.activity || {};
    const objectives = extended.objectives || {};
    const usage = extended.usage || {};
    target.innerHTML = `
        <div class="extended-grid">
            <section><h4>战斗承受</h4><dl>${[
                extendedMetric("英雄来源承伤", combat.hero_damage_taken),
                extendedMetric("总承伤", combat.total_damage_taken),
                extendedMetric("控制时长", combat.stuns_seconds, " 秒"),
                extendedMetric("英雄治疗", combat.hero_healing),
            ].join("")}</dl></section>
            <section><h4>经济与操作</h4><dl>${[
                extendedMetric("总获得金钱", economy.total_gold),
                extendedMetric("花费金钱", economy.gold_spent),
                extendedMetric("买活", economy.buyback_count, " 次"),
                extendedMetric("操作 / 分", activity.actions_per_min),
            ].join("")}</dl></section>
            <section><h4>控图与目标</h4><dl>${[
                extendedMetric("观察 / 岗哨", `${vision.observer_placed ?? "—"} / ${vision.sentry_placed ?? "—"}`),
                extendedMetric("排眼", (Number(vision.observer_destroyed) || 0) + (Number(vision.sentry_destroyed) || 0), " 次"),
                extendedMetric("堆野 / 符文", `${activity.camps_stacked ?? "—"} / ${activity.rune_pickups ?? "—"}`),
                extendedMetric("塔 / 肉山击杀", `${objectives.tower_kills ?? "—"} / ${objectives.roshan_kills ?? "—"}`),
            ].join("")}</dl></section>
            <section><h4>高频使用</h4><div class="usage-columns"><ol>${usageRows(usage.top_item_uses) || "<li>无物品使用记录</li>"}</ol><ol>${usageRows(usage.top_ability_uses) || "<li>无技能使用记录</li>"}</ol></div></section>
        </div>`;
}

function timelineImpactGroup(title, windows, metricLabel) {
    if (!windows?.length) return "";
    const rows = windows.map((window) => `
        <li><span>${escapeHtml(window.label || `${window.start_minute}-${window.end_minute}分钟`)}</span><strong>${numberLabel(window.total)} ${metricLabel}</strong></li>`).join("");
    return `<section><h4>${title}</h4><ol>${rows}</ol></section>`;
}

function renderTimeline(timeline) {
    const target = document.querySelector("[data-timeline]");
    if (!timeline?.available) {
        target.innerHTML = '<p class="muted-copy">分钟级时间线未返回。</p>';
        return;
    }
    const phases = (timeline.phases || []).map((phase) => `
        <div class="phase-cell">
            <span>${escapeHtml(phase.label)} 分钟</span>
            <strong>${numberLabel(phase.last_hits)} 补刀</strong>
            <small>${Number(phase.lh_per_min || 0).toFixed(1)} LH/min · ${numberLabel(phase.avg_gpm)} GPM · ${numberLabel(phase.avg_xpm)} XPM</small>
        </div>`).join("");
    const lowWindows = (timeline.low_efficiency_windows || []).map((window) => `
        <li><i data-lucide="activity" aria-hidden="true"></i><span><strong>${escapeHtml(window.label || `${window.start_minute}-${window.end_minute} 分钟`)}</strong><small>${Number(window.avg_lh || 0).toFixed(1)} LH/min</small></span></li>`).join("");
    const impactWindows = [
        timelineImpactGroup("输出高峰", timeline.damage_windows, "英雄伤害"),
        timelineImpactGroup("推塔高峰", timeline.tower_windows, "建筑伤害"),
    ].filter(Boolean).join("");
    target.innerHTML = `
        <div class="timeline-keyfacts">
            <div><span>10 分钟补刀</span><strong>${numberLabel(timeline.ten_min_last_hits)}</strong></div>
            <div><span>20 分钟补刀</span><strong>${numberLabel(timeline.twenty_min_last_hits)}</strong></div>
            <div><span>时间线来源</span><strong>${escapeHtml(timeline.source_label || timeline.source || "已解析")}</strong></div>
        </div>
        <div class="phase-grid">${phases}</div>
        ${impactWindows ? `<div class="timeline-impact-grid">${impactWindows}</div>` : ""}
        ${lowWindows ? `<div class="timeline-alerts"><h4>低效率窗口</h4><ul>${lowWindows}</ul></div>` : ""}`;
    refreshIcons();
}

function deathRow(death, index) {
    const contexts = (death.context_lines || []).map((line) => `<small>${escapeHtml(line.text)}</small>`).join("");
    const killer = death.killer_hero_name ? ` · ${escapeHtml(death.killer_hero_name)}` : "";
    return `<li><span class="event-time">${minuteLabel(death.minute)}</span><div><strong>死亡 ${index + 1}${killer}</strong>${death.position_label ? `<small>${escapeHtml(death.position_label)}</small>` : ""}${contexts}</div></li>`;
}

function purchaseRow(purchase) {
    return `<li><span class="event-time">${minuteLabel(purchase.minute)}</span><div><strong>${escapeHtml(purchase.item_name || `物品 #${purchase.item_id}`)}</strong><small>关键装备完成</small></div></li>`;
}

function coordinate(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(255, parsed)) : fallback;
}

function renderDeathCoordinateMap(events) {
    const points = (events?.death_map_points || []).slice(0, 12);
    if (!points.length) return "";
    const clusters = (events?.death_position_clusters || []).slice(0, 6);
    const rings = clusters.map((cluster) => `
        <circle class="death-coordinate-ring" cx="${coordinate(cluster.plot_x)}" cy="${coordinate(cluster.plot_y)}" r="${Math.max(8, Math.min(40, Number(cluster.radius) || 12))}">
            <title>${escapeHtml(cluster.evidence_label || "重复死亡坐标簇")}</title>
        </circle>`).join("");
    const dots = points.map((point, index) => `
        <g>
            <circle class="death-coordinate-dot" cx="${coordinate(point.plot_x, coordinate(point.x))}" cy="${coordinate(point.plot_y, 255 - coordinate(point.y))}" r="6">
                <title>${escapeHtml(point.label || `${minuteLabel(point.minute)} x=${point.x},y=${point.y}`)}</title>
            </circle>
            <text class="death-coordinate-number" x="${coordinate(point.plot_x, coordinate(point.x))}" y="${coordinate(point.plot_y, 255 - coordinate(point.y)) + 2}">${index + 1}</text>
        </g>`).join("");
    const chips = points.map((point, index) => `
        <li><b>${index + 1}</b><span>${escapeHtml(point.label || `${minuteLabel(point.minute)} x=${point.x},y=${point.y}`)}</span></li>`).join("");
    return `
        <section class="death-coordinate-panel" aria-labelledby="death-coordinate-title">
            <header><div><h4 id="death-coordinate-title">死亡坐标图</h4><small>只展示原始坐标，不生成地图区域名</small></div><span>${points.length} 个点</span></header>
            <svg class="death-coordinate-plot" viewBox="0 0 255 255" role="img" aria-label="死亡原始坐标图">
                <rect class="death-coordinate-bg" x="0" y="0" width="255" height="255" rx="6"></rect>
                <line class="death-coordinate-axis" x1="127.5" y1="0" x2="127.5" y2="255"></line>
                <line class="death-coordinate-axis" x1="0" y1="127.5" x2="255" y2="127.5"></line>
                ${rings}${dots}
            </svg>
            <ol class="death-coordinate-list">${chips}</ol>
        </section>`;
}

function renderEvents(events) {
    const target = document.querySelector("[data-events]");
    const deaths = events?.deaths || [];
    const purchases = events?.key_purchases || [];
    target.innerHTML = `
        <section class="event-group"><header><h4>死亡时间点</h4><span>${escapeHtml(events?.death_coverage_label || `${deaths.length} 次`)}</span></header><ol>${deaths.map(deathRow).join("") || "<li><div><strong>本局无死亡事件</strong></div></li>"}</ol></section>
        <section class="event-group"><header><h4>关键装备</h4><span>${purchases.length} 件</span></header><ol>${purchases.map(purchaseRow).join("") || "<li><div><strong>未识别关键装备完成点</strong></div></li>"}</ol></section>
        ${renderDeathCoordinateMap(events)}`;
}

function renderFindings(findings) {
    const target = document.querySelector("[data-findings]");
    target.innerHTML = (findings || []).map((finding) => `
        <article class="finding-item priority-${escapeHtml(finding.priority || "low")}">
            <header><span>${escapeHtml(finding.priority_label || finding.priority || "")}</span><h4>${escapeHtml(finding.title || finding.category_label || finding.category)}</h4>${finding.formula_score !== undefined ? `<b>${numberLabel(finding.formula_score)} 分</b>` : ""}</header>
            <p class="finding-evidence">${escapeHtml(finding.evidence)}</p>
            <p>${escapeHtml(finding.why_it_matters)}</p>
            <div><strong>下一局</strong><span>${escapeHtml(finding.action)}</span></div>
            ${finding.formula ? `<details><summary>排序公式</summary><code>${escapeHtml(finding.formula)}</code><ul>${(finding.formula_inputs || []).map(formulaInputRow).join("")}</ul></details>` : ""}
        </article>`).join("");
}

function renderDataLimits(limits, fieldLedger) {
    const list = Array.isArray(limits) ? limits : [];
    const ledger = Array.isArray(fieldLedger) ? fieldLedger : [];
    const limitsPanel = document.querySelector("[data-limits]");
    const required = ledger.filter((item) => item.required && item.applicable);
    const complete = required.filter((item) => item.status === "available").length;
    const statusLabels = { available: "完整", partial: "部分", missing: "缺失", not_applicable: "不适用" };
    const sourceRows = ledger.map((item) => `
        <div class="evidence-source-row status-${escapeHtml(item.status || "missing")}">
            <span><strong>${escapeHtml(item.label || item.id || "字段")}${item.required && item.applicable ? " · 必需" : ""}</strong><small>${escapeHtml(item.source || "来源未记录")}</small></span>
            <span>${escapeHtml(item.coverage || "覆盖未记录")}</span>
            <b>${statusLabels[item.status] || "未知"}</b>
        </div>`).join("");
    document.querySelector("[data-limit-label]").textContent = list.length ? "数据缺口与字段覆盖账本" : "字段覆盖账本";
    document.querySelector("[data-limit-count]").textContent = required.length
        ? `${complete}/${required.length}`
        : String(list.length);
    document.querySelector("[data-limit-list]").innerHTML = `
        <section class="evidence-coverage"><h4>字段覆盖账本</h4>${sourceRows || '<p>未返回字段覆盖清单。</p>'}</section>
        <section class="limitation-list"><h4>数据缺口</h4>${list.length
            ? `<ul>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
            : '<p>本局核心复盘字段覆盖完整。</p>'}</section>`;
    limitsPanel.open = list.length > 0;
}

function renderReview(payload) {
    state.review = payload;
    const analysis = payload.analysis || {};
    const guidance = payload.guidance || {};
    document.querySelector("[data-review-mode]").textContent = `公式 v${numberLabel(payload.formula_version || guidance.formula_version)}`;
    document.querySelector("[data-coach-conclusion]").innerHTML = `<span>最重要结论</span><p>${escapeHtml(guidance.conclusion || "本局没有形成可发布结论。")}</p>`;
    renderFormulaScores(guidance);
    renderActions(guidance.next_actions);
    renderPerformanceContext(analysis);
    renderExtendedMetrics(analysis.extended_metrics || {});
    renderTimeline(analysis.timeline || {});
    renderEvents(analysis.events || {});
    renderFindings(guidance.review_points || analysis.review_findings || []);
    renderDataLimits(
        guidance.data_limits || analysis.data_quality?.limitations || [],
        analysis.data_quality?.field_ledger || [],
    );
    reviewOutput.hidden = false;
    setAnalysisButtonLabel();
    setPageStatus("真实比赛字段已完成公式计算。", "success");
    refreshIcons();
    reviewOutput.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadMatchDetail() {
    const payload = await apiFetch(`/api/matches/${matchId}`, { method: "GET", timeout: 45000 });
    renderFactualDetail(payload);
}

async function loadReviewStatus() {
    state.reviewStatus = await apiFetch(`/api/reviews/${matchId}/status`, { method: "GET" });
    setAnalysisButtonLabel();
}

async function generateReview() {
    setAnalysisBusy(true);
    setPageStatus(state.reviewStatus?.exists ? "正在读取已生成复盘…" : "正在获取证据并计算确定性公式…", "loading");
    try {
        let payload = null;
        for (let attempt = 0; attempt < MAX_REVIEW_POLL_ATTEMPTS; attempt += 1) {
            payload = await apiFetch(`/api/reviews/${matchId}`, { method: "POST", timeout: 45000 });
            if (payload.status !== "processing") break;
            const retrySeconds = Math.max(1, Number(payload.retry_after_seconds) || 5);
            analyzeButton.querySelector("span").textContent = "正在解析比赛…";
            setPageStatus(`正在获取真实分钟与事件数据（${attempt + 1}/${MAX_REVIEW_POLL_ATTEMPTS}）…`, "loading");
            await wait(retrySeconds * 1000);
        }
        if (!payload || payload.status === "processing") {
            throw new Error("比赛事件仍在解析，稍后点击重试即可继续；系统不会生成缺证据建议。");
        }
        renderReview(payload);
    } catch (error) {
        setPageStatus(error.message, "error");
        analyzeButton.querySelector("span").textContent = "重试生成复盘";
    } finally {
        setAnalysisBusy(false);
    }
}

async function initMatchPage() {
    if (!matchId) {
        setPageStatus("比赛编号无效，请返回最近 10 局重新选择。", "error");
        return;
    }
    document.querySelector("[data-match-id]").textContent = `比赛 #${matchId}`;
    const results = await Promise.allSettled([loadMatchDetail(), loadReviewStatus()]);
    if (results[0].status === "rejected") {
        setPageStatus(results[0].reason?.message || "比赛详情加载失败。", "error");
    }
}

analyzeButton.addEventListener("click", generateReview);
refreshIcons();
initMatchPage();
