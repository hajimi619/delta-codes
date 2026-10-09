/**
 * 三角洲改枪码库 · 在线编辑后端
 *
 * Cloudflare Worker + D1。提供三个接口：
 *   GET  /api/changes        拉取全部改动（新增 + 失效标记）
 *   POST /api/add            新增一个改枪码
 *   POST /api/flag           把一个改枪码标记为失效 / 恢复
 *
 * 设计：基础 347 条数据留在仓库的 data/codes.json 里（只读、有 git 历史），
 * D1 里只存"改动"。前端把两者合并出最终列表。这样即使 D1 被清空，
 * 基础数据也还在，重新抓一次就恢复。
 */

const ALLOWED_ORIGINS = [
  "https://hajimi619.github.io",
  "http://localhost:8080",
  "http://127.0.0.1:8080",
];

// 与前端 / build_site.py 保持一致的玩法列表
const MODES = ["烽火地带", "全面战场", "烽火高操速T0", "黑潮爆破"];

const CODE_RE = /^[0-9A-Za-z]{8,32}$/;
const MAX_PER_IP_PER_HOUR = 30;

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  // file:// 打开时 Origin 是字面量 "null"
  const allow = origin === "null" || ALLOWED_ORIGINS.includes(origin) ? origin || "*" : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(data, headers, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

/** 去掉控制字符、压缩空白、限长 */
function clean(value, max) {
  return String(value == null ? "" : value)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

async function hashIp(ip) {
  const data = new TextEncoder().encode("delta-codes::" + ip);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

async function assertUnderRateLimit(env, ipHash) {
  const since = new Date(Date.now() - 3600 * 1000).toISOString();
  const row = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM changes WHERE ip_hash = ? AND created_at > ?"
  ).bind(ipHash, since).first();
  if (row && row.n >= MAX_PER_IP_PER_HOUR) {
    throw new Error("操作太频繁了，请过一会儿再试");
  }
}

async function listChanges(env) {
  const { results } = await env.DB.prepare(
    `SELECT id, type, target_id, status, gun, build, tab, mode, code, author, created_at
       FROM changes ORDER BY created_at ASC LIMIT 5000`
  ).all();
  return { changes: results || [] };
}

async function addCode(request, env) {
  const body = await request.json().catch(() => ({}));
  const gun = clean(body.gun, 24);
  const build = clean(body.build, 40);
  const tab = clean(body.tab, 20);
  const author = clean(body.author, 16);
  const code = String(body.code || "").trim();

  if (!gun) throw new Error("请填写枪械名");
  if (!author) throw new Error("请填写你的名字");
  if (!MODES.includes(tab)) throw new Error("请选择玩法");
  if (!CODE_RE.test(code)) throw new Error("改枪码格式不对（8–32 位字母数字，不要带横杠）");

  const ip = request.headers.get("CF-Connecting-IP") || "0.0.0.0";
  const ipHash = await hashIp(ip);
  await assertUnderRateLimit(env, ipHash);

  // 同一条码不允许重复提交（含已失效的）
  const dup = await env.DB.prepare("SELECT id FROM changes WHERE code = ? LIMIT 1").bind(code).first();
  if (dup) throw new Error("这条改枪码已经有人提交过了");

  const id = crypto.randomUUID();
  const mode = tab === "烽火高操速T0" ? "烽火地带" : tab;
  await env.DB.prepare(
    `INSERT INTO changes (id, type, target_id, status, gun, build, tab, mode, code, author, created_at, ip_hash)
     VALUES (?, 'add', NULL, 'valid', ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(id, gun, build, tab, mode, code, author, new Date().toISOString(), ipHash).run();

  return { ok: true, id: "user|" + id };
}

async function flagCode(request, env) {
  const body = await request.json().catch(() => ({}));
  const targetId = clean(body.target_id, 80);
  const status = body.status === "valid" ? "valid" : "invalid";
  if (!targetId) throw new Error("缺少目标改枪码");

  const ip = request.headers.get("CF-Connecting-IP") || "0.0.0.0";
  const ipHash = await hashIp(ip);
  await assertUnderRateLimit(env, ipHash);

  // 同一个人对同一条码的旧标记先删掉，只保留最新状态
  await env.DB.prepare("DELETE FROM changes WHERE type = 'flag' AND target_id = ? AND ip_hash = ?")
    .bind(targetId, ipHash).run();

  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO changes (id, type, target_id, status, gun, build, tab, mode, code, author, created_at, ip_hash)
     VALUES (?, 'flag', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)`
  ).bind(id, targetId, status, new Date().toISOString(), ipHash).run();

  return { ok: true, status };
}

export default {
  async fetch(request, env) {
    const headers = corsHeaders(request);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });

    const { pathname } = new URL(request.url);
    try {
      if (pathname === "/api/changes" && request.method === "GET") {
        return json(await listChanges(env), headers);
      }
      if (pathname === "/api/add" && request.method === "POST") {
        return json(await addCode(request, env), headers);
      }
      if (pathname === "/api/flag" && request.method === "POST") {
        return json(await flagCode(request, env), headers);
      }
      if (pathname === "/" || pathname === "/health") {
        return json({ ok: true, service: "delta-codes-api" }, headers);
      }
      return json({ error: "接口不存在" }, headers, 404);
    } catch (err) {
      return json({ error: String((err && err.message) || err) }, headers, 400);
    }
  },
};
