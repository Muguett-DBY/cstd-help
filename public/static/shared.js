const HERO_CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes";
const ITEM_CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items";

export class ApiError extends Error {
    constructor(message, code = "REQUEST_FAILED", status = 0) {
        super(message);
        this.name = "ApiError";
        this.code = code;
        this.status = status;
    }
}

export async function apiFetch(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeout || 30000);
    try {
        const response = await fetch(path, {
            ...options,
            headers: { Accept: "application/json", ...(options.headers || {}) },
            signal: controller.signal,
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch {
            payload = null;
        }
        if (!response.ok) {
            const error = payload?.error || {};
            throw new ApiError(error.message || `请求失败（HTTP ${response.status}）`, error.code, response.status);
        }
        return payload;
    } catch (error) {
        if (error?.name === "AbortError") {
            throw new ApiError("请求超时，请重试。", "REQUEST_TIMEOUT");
        }
        if (error instanceof ApiError) throw error;
        throw new ApiError("网络连接失败，已保留当前页面数据。", "NETWORK_ERROR");
    } finally {
        window.clearTimeout(timeout);
    }
}

export function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function safeSlug(value) {
    return /^[a-z0-9_]+$/.test(String(value || "")) ? String(value) : "";
}

export function heroImageUrl(hero) {
    const slug = safeSlug(hero?.slug);
    return slug ? `${HERO_CDN}/${slug}.png` : "";
}

export function itemImageUrl(item) {
    const slug = safeSlug(item?.slug);
    return slug ? `${ITEM_CDN}/${slug}.png` : "";
}

export function formatDuration(seconds) {
    const total = Number(seconds);
    if (!Number.isFinite(total) || total <= 0) return "—";
    const minutes = Math.floor(total / 60);
    const remain = Math.floor(total % 60);
    return `${minutes}:${String(remain).padStart(2, "0")}`;
}

export function formatLocalTime(value, includeYear = false) {
    if (!value) return "时间未知";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
        ...(includeYear ? { year: "numeric" } : {}),
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).format(date);
}

export function resultMeta(isWin) {
    if (isWin === true) return { key: "win", label: "胜利" };
    if (isWin === false) return { key: "loss", label: "失败" };
    return { key: "unknown", label: "待确认" };
}

export function laneRoleLabel(role) {
    const labels = { 1: "核心", 2: "游走", 3: "辅助" };
    return labels[Number(role)] || "位置未标注";
}

export function rankLabel(rankTier) {
    const value = Number(rankTier);
    if (!Number.isFinite(value) || value <= 0) return "段位未知";
    const medal = Math.floor(value / 10);
    const star = value % 10;
    const names = {
        1: "先锋",
        2: "卫士",
        3: "中军",
        4: "统帅",
        5: "传奇",
        6: "万古流芳",
        7: "超凡入圣",
        8: "冠世一绝",
    };
    return `${names[medal] || "段位"}${star ? ` ${star}` : ""}`;
}

export function numberLabel(value, suffix = "") {
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.round(number).toLocaleString("zh-CN")}${suffix}` : "—";
}

export function minuteLabel(value) {
    const minute = Number(value);
    return Number.isFinite(minute) ? `${minute.toFixed(1)} 分` : "时间未知";
}

export function refreshIcons() {
    window.requestAnimationFrame(() => window.lucide?.createIcons?.({ "stroke-width": 1.8 }));
}

export function attachImageFallbacks(root = document) {
    root.querySelectorAll("img[data-image-fallback]").forEach((image) => {
        image.addEventListener("error", () => {
            image.hidden = true;
            image.parentElement?.classList.add("image-missing");
        }, { once: true });
    });
}

export function getMatchId() {
    const raw = new URLSearchParams(window.location.search).get("id") || "";
    return /^\d{8,}$/.test(raw) ? raw : "";
}
