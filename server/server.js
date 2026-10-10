/**
 * 哈基米工具箱 · 改枪码接口服务
 *
 * 从 Cloudflare Worker 版本 (worker/worker.js) 原样搬过来，逻辑完全一致，
 * 只把 D1 换成同目录下的一个 JSON 文件（原子写入 + 串行化，够这个量级用）。
 *
 *   端口: 默认 3001，被 nginx 反代到 /api/*
 *   数据: /var/lib/hajimiovo/changes.json
 *
 * 路由:
 *   GET  /api/health    健康检查
 *   GET  /api/changes   拉取全部改动（新增 + 失效标记）
 *   POST /api/add       新增一个改枪码
 *   POST /api/flag      标记失效 / 恢复
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = parseInt(process.env.PORT || "3001", 10);
const DATA_DIR = process.env.DATA_DIR || "/var/lib/hajimiovo";
const STORE = path.join(DATA_DIR, "changes.json");

const MODES = ["烽火地带", "全面战场", "烽火高操速T0", "黑潮爆破"];
const CODE_RE = /^[0-9A-Za-z]{8,32}$/;
const MAX_PER_IP_PER_HOUR = 30;
const MAX_BODY = 8 * 1024;

/* 允许跨域的来源：自有域名 / GitHub 镜像 / 本地调试 */
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (origin === "null") return true;
  let host;
  try {
    host = new URL(origin).hostname;
  } catch (e) {
    return false;
  }
  return (
    host === "hajimiovo.top" ||
    host.endsWith(".hajimiovo.top") ||
    host === "hajimi619.github.io" ||
    host === "localhost" ||
    host === "127.0.0.1"
  );
}

/* ---------------- 存储：JSON 文件 + 原子写入 ---------------- */

let changes = [];
let writeChain = Promise.resolve();

function loadStore() {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    if (fs.existsSync(STORE)) {
      const raw = fs.readFileSync(STORE, "utf8");
      const parsed = JSON.parse(raw);
      changes = Array.isArray(parsed) ? parsed : parsed.changes || [];
    }
  } catch (e) {
    console.error("[store] 读取失败，从空开始:", e.message);
    changes = [];
  }
  console.log(`[store] 载入 ${changes.length} 条改动  文件=${STORE}`);
}

/** 串行化写入，避免并发覆盖；先写临时文件再 rename，保证不会写坏 */
function saveStore() {
  writeChain = writeChain.then(function () {
    return new Promise(function (resolve) {
      const tmp = STORE + ".tmp";
      const body = JSON.stringify({ changes: changes }, null, 0);
      fs.writeFile(tmp, body, "utf8", function (err) {
        if (err) {
          console.error("[store] 写临时文件失败:", err.message);
          return resolve();
        }
        fs.rename(tmp, STORE, function (err2) {
          if (err2) console.error("[store] rename 失败:", err2.message);
          resolve();
        });
      });
    });
  });
  return writeChain;
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
  return crypto
    .createHash("sha256")
    .update("delta-codes::" + ip)
    .digest("hex")
    .slice(0, 32);
}

function clientIp(req) {
  const xff = req.headers["x-forwarded-for"];
  if (xff) return String(xff).split(",")[0].trim();
  const real = req.headers["x-real-ip"];
  if (real) return String(real).trim();
  return (req.socket && req.socket.remoteAddress) || "0.0.0.0";
}

function corsHeaders(req) {
  const origin = req.headers.origin || "";
  const allow = isAllowedOrigin(origin) ? origin : "https://hajimiovo.top";
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
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
      if (size > MAX_BODY) {
        reject(new Error("请求体过大"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", function () {
      if (!chunks.length) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch (e) {
        reject(new Error("JSON 格式不对"));
      }
    });
    req.on("error", reject);
  });
}

function assertUnderRateLimit(ipHash) {
  const since = Date.now() - 3600 * 1000;
  const n = changes.filter(function (c) {
    return c.ip_hash === ipHash && Date.parse(c.created_at) > since;
  }).length;
  if (n >= MAX_PER_IP_PER_HOUR) throw new Error("操作太频繁了，请过一会儿再试");
}

/* ---------------- 业务 ---------------- */

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

  if (changes.some(function (c) { return c.code === code; })) {
    throw new Error("这条改枪码已经有人提交过了");
  }

  const id = crypto.randomUUID();
  const mode = tab === "烽火高操速T0" ? "烽火地带" : tab;
  changes.push({
    id: id, type: "add", target_id: null, status: "valid",
    gun: gun, build: build, tab: tab, mode: mode, code: code,
    author: author, created_at: new Date().toISOString(), ip_hash: ipHash,
  });
  saveStore();
  return { ok: true, id: "user|" + id };
}

function flagCode(body, req) {
  const targetId = clean(body.target_id, 80);
  const status = body.status === "valid" ? "valid" : "invalid";
  if (!targetId) throw new Error("缺少目标改枪码");

  const ipHash = hashIp(clientIp(req));
  assertUnderRateLimit(ipHash);

  /* 同一个 IP 对同一条码只保留最新的一次标记 */
  changes = changes.filter(function (c) {
    return !(c.type === "flag" && c.target_id === targetId && c.ip_hash === ipHash);
  });

  const id = crypto.randomUUID();
  changes.push({
    id: id, type: "flag", target_id: targetId, status: status,
    gun: null, build: null, tab: null, mode: null, code: null,
    author: null, created_at: new Date().toISOString(), ip_hash: ipHash,
  });
  saveStore();
  return { ok: true, status: status };
}

/* ---------------- HTTP ---------------- */

const server = http.createServer(function (req, res) {
  const headers = corsHeaders(req);
  const url = new URL(req.url, "http://localhost");
  const p = url.pathname.replace(/\/+$/, "") || "/";

  if (req.method === "OPTIONS") {
    res.writeHead(204, headers);
    return res.end();
  }

  if (req.method === "GET") {
    if (p === "/api/health" || p === "/" || p === "/health") {
      return sendJson(res, headers, 200, {
        ok: true, service: "delta-codes-api",
        records: changes.length, uptime: Math.round(process.uptime()),
      });
    }
    if (p === "/api/changes") {
      /* 对外不带 ip_hash */
      const out = changes.map(function (c) {
        return {
          id: c.id, type: c.type, target_id: c.target_id, status: c.status,
          gun: c.gun, build: c.build, tab: c.tab, mode: c.mode,
          code: c.code, author: c.author, created_at: c.created_at,
        };
      });
      return sendJson(res, headers, 200, { changes: out });
    }
    return sendJson(res, headers, 404, { error: "接口不存在" });
  }

  if (req.method === "POST") {
    if (p !== "/api/add" && p !== "/api/flag") {
      return sendJson(res, headers, 404, { error: "接口不存在" });
    }
    readBody(req).then(function (body) {
      try {
        const r = p === "/api/add" ? addCode(body || {}, req) : flagCode(body || {}, req);
        sendJson(res, headers, 200, r);
      } catch (e) {
        sendJson(res, headers, 400, { error: String((e && e.message) || e) });
      }
    }).catch(function (e) {
      sendJson(res, headers, 400, { error: String((e && e.message) || e) });
    });
    return;
  }

  sendJson(res, headers, 405, { error: "方法不支持" });
});

loadStore();
server.listen(PORT, "127.0.0.1", function () {
  console.log(`[api] 监听 127.0.0.1:${PORT}  (由 nginx 反代 /api/*)`);
});

process.on("SIGTERM", function () { server.close(function () { process.exit(0); }); });
process.on("SIGINT", function () { server.close(function () { process.exit(0); }); });
