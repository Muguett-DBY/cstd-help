import {
    apiFetch,
    attachImageFallbacks,
    escapeHtml,
    formatDuration,
    formatLocalTime,
    heroImageUrl,
    rankLabel,
    refreshIcons,
    resultMeta,
} from "/static/shared.js";

const refreshButton = document.querySelector("[data-refresh-matches]");
const refreshStatus = document.querySelector("[data-refresh-status]");
const syncTime = document.querySelector("[data-sync-time]");
const matchList = document.querySelector("[data-match-list]");
const listCount = document.querySelector("[data-list-count]");
const headerState = document.querySelector("[data-header-state]");
const state = { matches: [], refreshedAt: null, source: "cache" };

function setOperation(message, tone = "neutral") {
    refreshStatus.textContent = message || "";
    refreshStatus.dataset.tone = tone;
}

function setBusy(busy) {
    refreshButton.disabled = busy;
    refreshButton.setAttribute("aria-busy", String(busy));
    refreshButton.querySelector("svg")?.classList.toggle("spin", busy);
    matchList.setAttribute("aria-busy", String(busy));
}

function renderSummary(matches) {
    const known = matches.filter((match) => typeof match.is_win === "boolean");
    const wins = known.filter((match) => match.is_win).length;
    document.querySelector("[data-summary-count]").textContent = String(matches.length);
    document.querySelector("[data-summary-record]").textContent = known.length ? `${wins} 胜 ${known.length - wins} 负` : "—";
    document.querySelector("[data-summary-rate]").textContent = known.length ? `${Math.round(wins / known.length * 100)}%` : "—";
    document.querySelector("[data-summary-hero]").textContent = matches[0]?.hero?.name || "—";
    listCount.textContent = `${matches.length} / 10`;
}

function matchRow(match) {
    const result = resultMeta(match.is_win);
    const hero = match.hero || {};
    const image = heroImageUrl(hero);
    const kda = match.kda || {};
    const href = `/match.html?id=${encodeURIComponent(match.match_id)}`;
    return `
        <a class="match-row" href="${href}" data-result="${result.key}" aria-label="打开 ${escapeHtml(hero.name)} 比赛 ${escapeHtml(match.match_id)}">
            <span class="match-hero-cell">
                <span class="match-thumb ${image ? "" : "image-missing"}">
                    ${image ? `<img src="${image}" alt="" width="112" height="64" loading="lazy" data-image-fallback>` : ""}
                </span>
                <span><strong>${escapeHtml(hero.name || "未知英雄")}</strong><small>#${escapeHtml(match.match_id)}</small></span>
            </span>
            <span class="result-badge ${result.key}">${result.label}</span>
            <time datetime="${escapeHtml(match.ended_at || "")}">${escapeHtml(formatLocalTime(match.ended_at))}</time>
            <span class="mono">${formatDuration(match.duration_seconds)}</span>
            <span class="kda-line"><b>${Number(kda.kills) || 0}</b><i>/</i><b class="deaths">${Number(kda.deaths) || 0}</b><i>/</i><b>${Number(kda.assists) || 0}</b></span>
            <span>${escapeHtml(rankLabel(match.rank_tier))}</span>
            <i class="row-arrow" data-lucide="chevron-right" aria-hidden="true"></i>
        </a>`;
}

function renderMatchList(matches) {
    const limited = Array.isArray(matches) ? matches.slice(0, 10) : [];
    state.matches = limited;
    renderSummary(limited);
    if (!limited.length) {
        matchList.innerHTML = `
            <div class="empty-state">
                <i data-lucide="history" aria-hidden="true"></i>
                <strong>还没有比赛缓存</strong>
                <span>点击右上角刷新比赛</span>
            </div>`;
    } else {
        matchList.innerHTML = limited.map(matchRow).join("");
    }
    attachImageFallbacks(matchList);
    refreshIcons();
}

function applyPayload(payload, fallback = false) {
    state.refreshedAt = payload?.refreshed_at || null;
    state.source = fallback ? "seed" : (payload?.source || "cache");
    renderMatchList(payload?.matches || []);
    syncTime.textContent = state.refreshedAt
        ? `上次同步 ${formatLocalTime(state.refreshedAt, true)}${fallback ? " · 本地种子" : ""}`
        : "尚未同步比赛";
    headerState.innerHTML = `<span aria-hidden="true"></span>${fallback ? "离线缓存" : "缓存就绪"}`;
}

async function loadSeedMatches() {
    const response = await fetch("/matches.json", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("seed unavailable");
    return response.json();
}

async function loadCachedMatches() {
    setBusy(true);
    try {
        const payload = await apiFetch("/api/matches", { method: "GET" });
        if (payload?.matches?.length) {
            applyPayload(payload, false);
            setOperation("已读取比赛缓存。", "success");
        } else {
            const seed = await loadSeedMatches();
            applyPayload(seed, true);
            setOperation("当前显示最近一次发布的比赛缓存。", "neutral");
        }
    } catch {
        try {
            const seed = await loadSeedMatches();
            applyPayload(seed, true);
            setOperation("API 暂不可达，当前显示本地缓存。", "warning");
        } catch {
            renderMatchList([]);
            setOperation("比赛缓存读取失败，请点击刷新重试。", "error");
        }
    } finally {
        setBusy(false);
    }
}

async function refreshMatches() {
    setBusy(true);
    setOperation("正在同步最新天梯比赛…", "loading");
    try {
        const payload = await apiFetch("/api/matches/refresh", { method: "POST", timeout: 45000 });
        applyPayload(payload, false);
        setOperation(payload.rate_limited ? "刚刚已经同步，当前列表未变化。" : `已同步 ${payload.matches?.length || 0} 场比赛。`, "success");
    } catch (error) {
        setOperation(error.message, "error");
    } finally {
        setBusy(false);
    }
}

refreshButton.addEventListener("click", refreshMatches);
refreshIcons();
loadCachedMatches();
