/**
 * 哈基米工具箱 · 改枪码接口服务
 *
 *   端口: 默认 3001（nginx 反代 /api/*）
 *   数据: /var/lib/hajimiovo/changes.json   网友改动
 *         /var/lib/hajimiovo/admin.json     管理员凭据（由 set_admin.py 写入）
 *         /var/lib/hajimiovo/tokens.json    登录令牌（重启不掉线）
 *
 * 公开接口:
 *   GET  /api/health
 *   GET  /api/changes
 *   POST /api/add             新增一个改枪码
 *   POST /api/flag            标记失效 / 恢复
 *
 * 基米餐馆（菜单只放服务器上，客户端不可能绕过密码）:
 *   POST /api/restaurant/unlock  {password} -> {token}
 *   GET  /api/restaurant/menu    (Bearer)   -> 菜单
 *
 * 管理员接口（需 Authorization: Bearer <token>）:
 *   POST /api/admin/login     {username, password} -> {token}
 *   POST /api/admin/logout
 *   GET  /api/admin/me
 *   POST /api/admin/delete    {target_id, undo}   软删除 / 撤销删除（基础数据和网友新增都能删）
 *   POST /api/admin/purge     {target_id}         永久删除（仅网友新增，物理移除）
 *   POST /api/admin/edit      {target_id, gun, build, tab, mode, code}
 *   POST /api/admin/clearflags{target_id}         清除失效标记（不给 target_id 就是全清）
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = parseInt(process.env.PORT || "3001", 10);
const DATA_DIR = process.env.DATA_DIR || "/var/lib/hajimiovo";
const STORE = path.join(DATA_DIR, "changes.json");
const ADMIN_FILE = path.join(DATA_DIR, "admin.json");
const TOKEN_FILE = path.join(DATA_DIR, "tokens.json");
/* 基米餐馆：密码和菜单都只在服务器上，静态文件里一个字都不放 */
const GUEST_FILE = path.join(DATA_DIR, "restaurant.json");
const RMENU_FILE = path.join(DATA_DIR, "restaurant-menu.json");
const RTOKEN_FILE = path.join(DATA_DIR, "restaurant-tokens.json");

const MODES = ["烽火地带", "全面战场", "烽火高操速T0", "黑潮爆破"];
const CODE_RE = /^[0-9A-Za-z]{8,32}$/;
const MAX_PER_IP_PER_HOUR = 30;
const MAX_BODY = 16 * 1024;
const TOKEN_TTL_MS = 30 * 24 * 3600 * 1000;   // 登录 30 天有效
const LOGIN_MAX_FAIL = 8;                      // 单 IP 15 分钟内最多失败次数
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const R_TOKEN_TTL_MS = 12 * 3600 * 1000;       // 餐馆密码通过后 12 小时有效
const R_MAX_FAIL = 6;                          // 餐馆密码单 IP 15 分钟最多错 6 次

/* ---------------- CORS ---------------- */

function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (origin === "null") return true;
  let host;
  try { host = new URL(origin).hostname; } catch (e) { return false; }
  return (
    host === "hajimiovo.top" || host.endsWith(".hajimiovo.top") ||
    host === "hajimi619.github.io" || host === "localhost" || host === "127.0.0.1"
  );
}

function corsHeaders(req) {
  const origin = req.headers.origin || "";
  const allow = isAllowedOrigin(origin) ? origin : "https://hajimiovo.top";
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

/* ---------------- 存储 ---------------- */

let changes = [];
let tokens = {};
let rTokens = {};             // 餐馆访客令牌
let loginFails = {};          // ipHash -> [时间戳]
let rFails = {};              // 餐馆密码错误次数
let writeChain = Promise.resolve();

function loadJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    const raw = fs.readFileSync(file, "utf8");
    const d = JSON.parse(raw);
    return d == null ? fallback : d;
  } catch (e) {
    console.error(`[store] 读取 ${file} 失败:`, e.message);
    return fallback;
  }
}

function saveJson(file, obj) {
  writeChain = writeChain.then(function () {
    return new Promise(function (resolve) {
      const tmp = file + ".tmp";
      fs.writeFile(tmp, JSON.stringify(obj), "utf8", function (err) {
        if (err) { console.error("[store] 写失败:", err.message); return resolve(); }
        fs.rename(tmp, file, function (e2) {
          if (e2) console.error("[store] rename 失败:", e2.message);
          resolve();
        });
      });
    });
  });
  return writeChain;
}

function loadAll() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const cd = loadJson(STORE, { changes: [] });
  changes = Array.isArray(cd) ? cd : cd.changes || [];
  tokens = loadJson(TOKEN_FILE, {});
  // 清掉过期令牌
  const now = Date.now();
  let n = 0;
  Object.keys(tokens).forEach(function (t) {
    if (!tokens[t] || tokens[t].expires < now) { delete tokens[t]; n++; }
  });
  console.log(`[store] 改动 ${changes.length} 条, 有效令牌 ${Object.keys(tokens).length} 个` + (n ? `（清理过期 ${n} 个）` : ""));
  console.log(`[store] 管理员凭据: ${fs.existsSync(ADMIN_FILE) ? "已配置" : "❌ 未配置（跑 set_admin.py）"}`);

  // 餐馆访客令牌
  rTokens = loadJson(RTOKEN_FILE, {});
  const now2 = Date.now();
  Object.keys(rTokens).forEach(function (t) {
    if (!rTokens[t] || rTokens[t].expires < now2) delete rTokens[t];
  });
  const g = loadJson(GUEST_FILE, null);
  let menuCount = 0;
  try {
    const m = loadJson(RMENU_FILE, null);
    if (m && m.cuisines) menuCount = m.cuisines.reduce(function (a, c) { return a + c.dishes.length; }, 0);
  } catch (e) { /* ignore */ }
  console.log(`[store] 基米餐馆: 密码${g && g.hash ? "已配置" : "❌ 未配置（跑 set_restaurant.py）"}` +
              `, 菜单 ${menuCount} 道菜, 访客令牌 ${Object.keys(rTokens).length} 个`);
}

/* ---------------- 工具 ---------------- */

function clean(v, max) {
  return String(v == null ? "" : v)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

function hashIp(ip) {
  return crypto.createHash("sha256").update("delta-codes::" + ip).digest("hex").slice(0, 32);
}

function clientIp(req) {
  const xff = req.headers["x-forwarded-for"];
  if (xff) return String(xff).split(",")[0].trim();
  if (req.headers["x-real-ip"]) return String(req.headers["x-real-ip"]).trim();
  return (req.socket && req.socket.remoteAddress) || "0.0.0.0";
}

function sendJson(res, headers, status, obj) {
  const body = Buffer.from(JSON.stringify(obj), "utf8");
  res.writeHead(status, Object.assign({}, headers, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": body.length,
  }));
  res.end(body);
}

function readBody(req) {
  return new Promise(function (resolve, reject) {
    let size = 0;
    const chunks = [];
    req.on("data", function (c) {
      size += c.length;
      if (size > MAX_BODY) { reject(new Error("请求体过大")); req.destroy(); return; }
      chunks.push(c);
    });
    req.on("end", function () {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
      catch (e) { reject(new Error("JSON 格式不对")); }
    });
    req.on("error", reject);
  });
}

function assertUnderRateLimit(ipHash) {
  const since = Date.now() - 3600 * 1000;
  const n = changes.filter(function (c) {
    return c.ip_hash === ipHash && c.type !== "edit" && c.type !== "delete" &&
           Date.parse(c.created_at) > since;
  }).length;
  if (n >= MAX_PER_IP_PER_HOUR) throw new Error("操作太频繁了，请过一会儿再试");
}

/* ---------------- 管理员鉴权 ---------------- */

function loadAdmin() {
  return loadJson(ADMIN_FILE, null);
}

function hashPassword(pwd, salt) {
  return crypto.scryptSync(pwd, salt, 64).toString("hex");
}

function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}

function findToken(req) {
  const h = req.headers.authorization || "";
  const m = /^Bearer\s+(.+)$/i.exec(h.trim());
  return m ? m[1].trim() : "";
}

/** 校验令牌；失败抛错
    除了有效期，还要比对凭据版本 ver —— 这样改了用户名/密码之后，
    所有旧令牌立刻失效，不用手动去清 tokens.json。 */
function requireAdmin(req) {
  const t = findToken(req);
  if (!t) throw new Error("请先登录管理员");
  const rec = tokens[t];
  if (!rec) throw new Error("登录已失效，请重新登录");
  if (rec.expires < Date.now()) {
    delete tokens[t];
    saveJson(TOKEN_FILE, tokens);
    throw new Error("登录已过期，请重新登录");
  }
  const a = loadAdmin();
  if (!a || !a.username) throw new Error("服务器还没配置管理员账号");
  if (a.ver && rec.ver !== a.ver) {
    delete tokens[t];
    saveJson(TOKEN_FILE, tokens);
    throw new Error("管理员凭据已变更，请重新登录");
  }
  return rec.username;
}

function adminLogin(body, req) {
  const a = loadAdmin();
  if (!a || !a.username || !a.hash) throw new Error("服务器还没配置管理员账号");

  const ip = hashIp(clientIp(req));
  const now = Date.now();
  loginFails[ip] = (loginFails[ip] || []).filter(function (t) { return now - t < LOGIN_WINDOW_MS; });
  if (loginFails[ip].length >= LOGIN_MAX_FAIL) {
    throw new Error("登录失败次数过多，请 15 分钟后再试");
  }

  const username = clean(body.username, 32);
  const password = String(body.password || "");
  if (!username || !password) throw new Error("请填写用户名和密码");

  const ok = safeEqual(username, a.username) && safeEqual(hashPassword(password, a.salt), a.hash);
  if (!ok) {
    loginFails[ip].push(now);
    throw new Error("用户名或密码不对");
  }

  loginFails[ip] = [];
  const token = crypto.randomBytes(32).toString("hex");
  tokens[token] = {
    username: username,
    ver: a.ver || "",
    expires: now + TOKEN_TTL_MS,
    created_at: new Date().toISOString(),
  };
  saveJson(TOKEN_FILE, tokens);
  return { ok: true, username: username, token: token, expires: tokens[token].expires };
}

/* ---------------- 公开业务 ---------------- */

function addCode(body, req) {
  const gun = clean(body.gun, 24);
  const build = clean(body.build, 40);
  const tab = clean(body.tab, 20);
  const author = clean(body.author, 16);
  const code = String(body.code || "").trim();

  if (!gun) throw new Error("请填写枪械名");
  if (!author) throw new Error("请填写你的名字");
  if (MODES.indexOf(tab) < 0) throw new Error("请选择玩法");
  if (!CODE_RE.test(code)) throw new Error("改枪码格式不对（8–32 位字母数字，不要带横杠）");

  const ipHash = hashIp(clientIp(req));
  assertUnderRateLimit(ipHash);

  if (changes.some(function (c) { return c.code === code && c.type === "add"; })) {
    throw new Error("这条改枪码已经有人提交过了");
  }

  const id = crypto.randomUUID();
  changes.push({
    id: id, type: "add", target_id: null, status: "valid",
    gun: gun, build: build, tab: tab, mode: tab === "烽火高操速T0" ? "烽火地带" : tab,
    code: code, author: author, created_at: new Date().toISOString(), ip_hash: ipHash,
  });
  saveJson(STORE, { changes: changes });
  return { ok: true, id: "user|" + id };
}

function flagCode(body, req) {
  const targetId = clean(body.target_id, 80);
  const status = body.status === "valid" ? "valid" : "invalid";
  if (!targetId) throw new Error("缺少目标改枪码");

  const ipHash = hashIp(clientIp(req));
  assertUnderRateLimit(ipHash);

  changes = changes.filter(function (c) {
    return !(c.type === "flag" && c.target_id === targetId && c.ip_hash === ipHash);
  });
  const id = crypto.randomUUID();
  changes.push({
    id: id, type: "flag", target_id: targetId, status: status,
    gun: null, build: null, tab: null, mode: null, code: null, author: null,
    created_at: new Date().toISOString(), ip_hash: ipHash,
  });
  saveJson(STORE, { changes: changes });
  return { ok: true, status: status };
}

/* ---------------- 管理员业务 ---------------- */

/** target_id 可能是基础数据的 id（玩法|码），也可能是 user|<uuid> */
function isUserRecord(targetId) {
  return /^user\|/.test(targetId);
}

function adminDelete(body) {
  const targetId = clean(body.target_id, 80);
  if (!targetId) throw new Error("缺少目标");
  const undo = !!body.undo;

  changes = changes.filter(function (c) {
    return !(c.type === "delete" && c.target_id === targetId);
  });
  changes.push({
    id: crypto.randomUUID(), type: "delete", target_id: targetId,
    status: undo ? "valid" : "deleted",
    gun: null, build: null, tab: null, mode: null, code: null, author: null,
    created_at: new Date().toISOString(), ip_hash: null,
  });
  saveJson(STORE, { changes: changes });
  return { ok: true, deleted: !undo };
}

/** 永久删除：只对网友新增的内容生效，物理移除，不可恢复 */
function adminPurge(body) {
  const targetId = clean(body.target_id, 80);
  if (!targetId) throw new Error("缺少目标");
  if (!isUserRecord(targetId)) throw new Error("基础数据不能永久删除，只能隐藏");

  const rawId = targetId.slice(5);
  const before = changes.length;
  changes = changes.filter(function (c) {
    if (c.id === rawId) return false;                              // 那条 add 本身
    if (c.target_id === targetId) return false;                    // 针对它的 flag/delete/edit
    return true;
  });
  const removed = before - changes.length;
  saveJson(STORE, { changes: changes });
  return { ok: true, removed: removed };
}

function adminEdit(body) {
  const targetId = clean(body.target_id, 80);
  if (!targetId) throw new Error("缺少目标");

  const patch = {
    gun: clean(body.gun, 24),
    build: clean(body.build, 40),
    tab: clean(body.tab, 20),
    mode: null,
    code: String(body.code || "").trim(),
  };
  if (!patch.gun) throw new Error("枪械名不能为空");
  if (MODES.indexOf(patch.tab) < 0) throw new Error("请选择玩法");
  if (!CODE_RE.test(patch.code)) throw new Error("改枪码格式不对（8–32 位字母数字）");
  patch.mode = patch.tab === "烽火高操速T0" ? "烽火地带" : patch.tab;

  /* 同一个目标只保留最新的一次编辑 */
  changes = changes.filter(function (c) {
    return !(c.type === "edit" && c.target_id === targetId);
  });
  changes.push({
    id: crypto.randomUUID(), type: "edit", target_id: targetId, status: "valid",
    gun: patch.gun, build: patch.build, tab: patch.tab, mode: patch.mode,
    code: patch.code, author: null,
    created_at: new Date().toISOString(), ip_hash: null,
  });
  saveJson(STORE, { changes: changes });
  return { ok: true, patch: patch };
}

/** 清除失效标记；不给 target_id 就全清 */
function adminClearFlags(body) {
  const targetId = body.target_id ? clean(body.target_id, 80) : "";
  const before = changes.length;
  changes = changes.filter(function (c) {
    if (c.type !== "flag") return true;
    if (!targetId) return false;
    return c.target_id !== targetId;
  });
  const removed = before - changes.length;
  saveJson(STORE, { changes: changes });
  return { ok: true, removed: removed };
}

/* ---------------- 基米餐馆 ----------------
   菜单和密码都只存在服务器上（/var/lib/hajimiovo/），
   docs/ 里一个字都不放 —— 不然看源码就把密码绕过去了。 */

function loadGuest() {
  return loadJson(GUEST_FILE, null);
}

function restaurantUnlock(body, req) {
  const g = loadGuest();
  if (!g || !g.hash) throw new Error("餐馆还没设置密码");

  const ip = hashIp(clientIp(req));
  const now = Date.now();
  rFails[ip] = (rFails[ip] || []).filter(function (t) { return now - t < LOGIN_WINDOW_MS; });
  if (rFails[ip].length >= R_MAX_FAIL) throw new Error("密码错误次数过多，请 15 分钟后再试");

  const password = String(body.password || "");
  if (!password) throw new Error("请输入密码");
  if (!safeEqual(hashPassword(password, g.salt), g.hash)) {
    rFails[ip].push(now);
    throw new Error("密码不对");
  }

  rFails[ip] = [];
  const token = crypto.randomBytes(32).toString("hex");
  rTokens[token] = {
    ver: g.ver || "",
    expires: now + R_TOKEN_TTL_MS,
    created_at: new Date().toISOString(),
  };
  saveJson(RTOKEN_FILE, rTokens);
  return { ok: true, token: token, expires: rTokens[token].expires };
}

function requireGuest(req) {
  const t = findToken(req);
  if (!t) throw new Error("请先输入密码");
  const rec = rTokens[t];
  if (!rec) throw new Error("请重新输入密码");
  if (rec.expires < Date.now()) {
    delete rTokens[t];
    saveJson(RTOKEN_FILE, rTokens);
    throw new Error("已超过 12 小时，请重新输入密码");
  }
  const g = loadGuest();
  if (g && g.ver && rec.ver !== g.ver) {
    delete rTokens[t];
    saveJson(RTOKEN_FILE, rTokens);
    throw new Error("密码已变更，请重新输入密码");
  }
  return true;
}

function restaurantMenu(req) {
  requireGuest(req);
  const m = loadJson(RMENU_FILE, null);
  if (!m || !m.cuisines) throw new Error("菜单还没准备好");
  return m;
}

/* ---------------- HTTP ---------------- */

function publicChanges() {
  return changes
    .filter(function (c) { return c.type !== "delete" || c.status !== "valid"; })  // 保留删除记录给前端
    .map(function (c) {
      return {
        id: c.id, type: c.type, target_id: c.target_id, status: c.status,
        gun: c.gun, build: c.build, tab: c.tab, mode: c.mode,
        code: c.code, author: c.author, created_at: c.created_at,
      };
    });
}

const server = http.createServer(function (req, res) {
  const headers = corsHeaders(req);
  const p = (new URL(req.url, "http://localhost").pathname.replace(/\/+$/, "")) || "/";

  if (req.method === "OPTIONS") { res.writeHead(204, headers); return res.end(); }

  if (req.method === "GET") {
    if (p === "/" || p === "/health" || p === "/api/health") {
      const a = loadAdmin();
      return sendJson(res, headers, 200, {
        ok: true, service: "delta-codes-api",
        records: changes.length, uptime: Math.round(process.uptime()),
        admin_configured: !!(a && a.username),
      });
    }
    if (p === "/api/changes") return sendJson(res, headers, 200, { changes: publicChanges() });
    if (p === "/api/restaurant/menu") {
      try {
        return sendJson(res, headers, 200, restaurantMenu(req));
      } catch (e) {
        return sendJson(res, headers, 401, { error: e.message });
      }
    }
    if (p === "/api/admin/me") {
      try {
        const u = requireAdmin(req);
        return sendJson(res, headers, 200, { ok: true, username: u });
      } catch (e) {
        return sendJson(res, headers, 401, { error: e.message });
      }
    }
    return sendJson(res, headers, 404, { error: "接口不存在" });
  }

  if (req.method === "POST") {
    const routes = {
      "/api/add": function (b, r) { return addCode(b, r); },
      "/api/flag": function (b, r) { return flagCode(b, r); },
      "/api/restaurant/unlock": function (b, r) { return restaurantUnlock(b, r); },
      "/api/admin/login": function (b, r) { return adminLogin(b, r); },
      "/api/admin/logout": function (b, r) {
        const t = findToken(r);
        if (t && tokens[t]) { delete tokens[t]; saveJson(TOKEN_FILE, tokens); }
        return { ok: true };
      },
      "/api/admin/delete": function (b, r) { requireAdmin(r); return adminDelete(b); },
      "/api/admin/purge": function (b, r) { requireAdmin(r); return adminPurge(b); },
      "/api/admin/edit": function (b, r) { requireAdmin(r); return adminEdit(b); },
      "/api/admin/clearflags": function (b, r) { requireAdmin(r); return adminClearFlags(b); },
    };
    const fn = routes[p];
    if (!fn) return sendJson(res, headers, 404, { error: "接口不存在" });
    readBody(req).then(function (body) {
      try { sendJson(res, headers, 200, fn(body || {}, req)); }
      catch (e) { sendJson(res, headers, 400, { error: String((e && e.message) || e) }); }
    }).catch(function (e) {
      sendJson(res, headers, 400, { error: String((e && e.message) || e) });
    });
    return;
  }

  sendJson(res, headers, 405, { error: "方法不支持" });
});

loadAll();
server.listen(PORT, "127.0.0.1", function () {
  console.log(`[api] 监听 127.0.0.1:${PORT}  (由 nginx 反代 /api/*)`);
});

process.on("SIGTERM", function () { server.close(function () { process.exit(0); }); });
process.on("SIGINT", function () { server.close(function () { process.exit(0); }); });
