/**
 * Cloudflare Worker：定時排程 + 密碼手動刷新，兩條路都是去戳 GitHub Actions。
 *
 * 為什麼不用 GitHub 自己的 schedule：
 *   * GitHub 的排程常延遲 10~30 分鐘，尖峰更久，半小時一次的節奏會被打亂
 *   * 對 60 天沒有 commit 活動的 repo，GitHub 會自動停用 cron
 *   Cloudflare Cron Triggers 準時得多，免費方案就有。
 *
 * GitHub token 只放在 Worker 的 secret 裡，永遠不會出現在前端。
 *
 * 需要的設定（見 wrangler.toml）：
 *   secret  REFRESH_PASSWORD   手動刷新用的密碼
 *   secret  GITHUB_TOKEN       fine-grained PAT，只要 Actions: read & write
 *   var     GITHUB_REPO        "owner/repo"
 *   var     WORKFLOW_FILE      "fetch.yml"
 *   var     GITHUB_REF         "main"
 *   var     ALLOWED_ORIGINS    逗號分隔；留空代表不限制
 *   kv      RATE_LIMIT         選用，沒綁就不做頻率限制
 */

const COOLDOWN_SECONDS = 120;   // 手動刷新兩次之間至少隔多久

export default {
  // ---- 定時排程：每 30 分鐘由 Cloudflare 觸發，不需要密碼 ----
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const r = await dispatch(env);
      console.log(r.ok ? `scheduled dispatch ok @ ${new Date(event.scheduledTime).toISOString()}`
                       : `scheduled dispatch failed: ${r.status} ${r.detail}`);
    })());
  },

  // ---- 手動刷新：前端 POST { password } ----
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin, env);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405, cors);
    if (!originAllowed(origin, env)) return json({ ok: false, error: "origin_not_allowed" }, 403, cors);

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "bad_json" }, 400, cors);
    }

    const expected = env.REFRESH_PASSWORD || "";
    if (!expected) return json({ ok: false, error: "not_configured" }, 500, cors);
    if (!timingSafeEqual(String(body?.password ?? ""), expected)) {
      // 密碼錯也計入冷卻，免得有人拿這支介面慢慢猜
      await touchRateLimit(env, request);
      return json({ ok: false, error: "wrong_password" }, 401, cors);
    }

    const wait = await checkRateLimit(env, request);
    if (wait > 0) return json({ ok: false, error: "too_soon", retry_after: wait }, 429, cors);

    const r = await dispatch(env);
    if (r.ok) {
      await touchRateLimit(env, request);
      return json({ ok: true }, 200, cors);
    }
    return json({ ok: false, error: r.error, status: r.status, detail: r.detail }, r.code, cors);
  },
};

// ---------------------------------------------------------------- 觸發

async function dispatch(env) {
  const repo = env.GITHUB_REPO;
  const workflow = env.WORKFLOW_FILE || "fetch.yml";
  const ref = env.GITHUB_REF || "main";
  if (!repo || !env.GITHUB_TOKEN) {
    return { ok: false, error: "not_configured", code: 500, status: 0, detail: "" };
  }

  const res = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sky-price-refresh-worker",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref }),
    }
  );

  if (res.status === 204) return { ok: true };
  // 把 GitHub 的錯誤帶一點上來方便排查，但不外洩 token
  const detail = await res.text().catch(() => "");
  return { ok: false, error: "dispatch_failed", code: 502,
           status: res.status, detail: detail.slice(0, 300) };
}

// ---------------------------------------------------------------- 工具

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

const allowedList = (env) =>
  (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);

function originAllowed(origin, env) {
  const list = allowedList(env);
  if (!list.length) return true;   // 沒設就不限制
  if (!origin) return true;        // 非瀏覽器來源不擋，密碼才是主要防線
  return list.includes(origin);
}

function corsHeaders(origin, env) {
  const list = allowedList(env);
  const allow = !list.length ? "*" : (list.includes(origin) ? origin : list[0]);
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

/** 長度不同也要跑完整個迴圈，不要讓比對時間洩漏密碼長度。 */
function timingSafeEqual(a, b) {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

const rateKey = (request) =>
  `refresh:${request.headers.get("CF-Connecting-IP") || "shared"}`;

async function checkRateLimit(env, request) {
  if (!env.RATE_LIMIT) return 0;   // 沒綁 KV 就不限制
  const last = await env.RATE_LIMIT.get(rateKey(request));
  if (!last) return 0;
  const elapsed = Math.floor((Date.now() - Number(last)) / 1000);
  return elapsed >= COOLDOWN_SECONDS ? 0 : COOLDOWN_SECONDS - elapsed;
}

async function touchRateLimit(env, request) {
  if (!env.RATE_LIMIT) return;
  await env.RATE_LIMIT.put(rateKey(request), String(Date.now()),
                           { expirationTtl: Math.max(60, COOLDOWN_SECONDS) });
}
