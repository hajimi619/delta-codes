/* ============================================================
   哈基米工具箱 · Service Worker
   目标：国内到 Cloudflare 的握手经常 10 秒以上甚至超时，
        所以让"第二次之后的访问"完全不依赖网络。
   - 页面(HTML)  ：网络优先，2.5 秒没回来就用缓存
   - 静态资源    ：缓存优先，后台静默更新
   - data.js     ：缓存优先 + 后台更新（stale-while-revalidate）
   - /api/changes：网络优先，2 秒超时回退到上次结果
   ============================================================ */

var VERSION = "hk-v1";
var SHELL = "shell-" + VERSION;
var ASSET = "asset-" + VERSION;
var DATA = "data-" + VERSION;

/* 相对路径 → 自动适配根目录部署和 /delta-codes/ 子目录部署 */
var ROOT = self.registration.scope;
var OFFLINE_URL = ROOT + "404.html";
var API_RE = /\/api\/(changes|add|flag)/;

var PRECACHE = [
  ROOT,
  ROOT + "delta-codes/",
  ROOT + "assets/theme.css",
  ROOT + "assets/site.js",
  ROOT + "404.html"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(SHELL).then(function (c) {
      /* 逐个加，一个失败不影响其它 */
      return Promise.all(PRECACHE.map(function (u) {
        return c.add(new Request(u, { cache: "reload" })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== SHELL && k !== ASSET && k !== DATA) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

/** 带超时的 fetch，超时抛错以便回退到缓存 */
function timeoutFetch(req, ms) {
  return new Promise(function (resolve, reject) {
    var t = setTimeout(function () { reject(new Error("timeout")); }, ms);
    fetch(req).then(function (res) {
      clearTimeout(t);
      resolve(res);
    }, function (err) {
      clearTimeout(t);
      reject(err);
    });
  });
}

function put(cacheName, req, res) {
  if (res && res.ok && res.type !== "opaque") {
    var copy = res.clone();
    caches.open(cacheName).then(function (c) { c.put(req, copy); });
  }
  return res;
}

/** 页面导航：先给缓存（秒开），同时后台拉新的
    用 event.waitUntil 保证后台更新不会被中途掐断 */
function handleNavigation(req, event) {
  return caches.match(req).then(function (cached) {
    var network = timeoutFetch(req, 2500).then(function (res) {
      return put(SHELL, req, res);
    })["catch"](function () {
      return cached || caches.match(OFFLINE_URL);
    });
    if (event) event.waitUntil(network.then(function () {}).catch(function () {}));
    return cached || network;
  });
}

/** 静态资源：缓存优先，后台静默更新 */
function handleAsset(req, event) {
  return caches.match(req).then(function (cached) {
    var network = fetch(req).then(function (res) {
      return put(ASSET, req, res);
    })["catch"](function () { return cached; });
    if (event) event.waitUntil(network.then(function () {}).catch(function () {}));
    return cached || network;
  });
}

/** data.js：有缓存先用，后台更新 */
function handleData(req, event) {
  return caches.match(req).then(function (cached) {
    var network = fetch(req).then(function (res) {
      return put(DATA, req, res);
    })["catch"](function () { return cached; });
    if (event) event.waitUntil(network.then(function () {}).catch(function () {}));
    return cached || network;
  });
}

/** 接口：网络优先（2 秒），失败用上次结果 */
function handleApi(req) {
  return timeoutFetch(req, 2000).then(function (res) {
    return put(DATA, req, res);
  }).catch(function () {
    return caches.match(req).then(function (cached) {
      if (cached) return cached;
      return new Response(JSON.stringify({ changes: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8", "X-From-SW-Cache": "1" }
      });
    });
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;                       // 写操作不拦
  var url = new URL(req.url);

  if (API_RE.test(url.pathname)) {
    e.respondWith(handleApi(req));
    return;
  }
  if (url.origin !== self.location.origin) return;        // 其它跨域不拦

  if (req.mode === "navigate") { e.respondWith(handleNavigation(req, e)); return; }
  if (/\/data\.js$/.test(url.pathname)) { e.respondWith(handleData(req, e)); return; }
  if (/\.(css|js|webp|png|jpg|svg|woff2?|ico)$/.test(url.pathname) || url.pathname.indexOf("/assets/") >= 0) {
    e.respondWith(handleAsset(req, e));
  }
});
