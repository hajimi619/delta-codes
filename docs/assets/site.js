/* ============================================================
   哈基米工具箱 · 站点外壳
   功能清单在这里维护；首页卡片和每个页面顶部的切换导航都由它生成。
   加新功能 = 建一个文件夹 + 往下面这个数组里加一条。
   ============================================================ */
(function () {
  "use strict";

  var SITE = {
    name: "哈基米工具箱",
    slogan: "自己用得上，就顺手做出来",
    copyright: "© 2026 哈基米"
  };

  /* ---------------- 功能清单 ----------------
     id      唯一标识，也是所在文件夹名
     name    显示名
     desc    一句话说明
     tags    标签
     status  "online" 已上线 / "beta" 测试中 / "coming" 计划中
     icon    显示在卡片左上角的字符（emoji 或单字）
     stats   可选，卡片上的小数据
  ------------------------------------------- */
  var FEATURES = [
    {
      id: "delta-codes",
      name: "三角洲行动 · 改枪码库",
      desc: "按枪械分类浏览改枪码，支持价格筛选、收藏、对比、一键复制。所有人都能补充新码、标记失效。",
      tags: ["三角洲行动", "游戏工具"],
      status: "online",
      icon: "Δ",
      stats: [
        { label: "改枪码", value: "347+" },
        { label: "枪械", value: "67" },
        { label: "玩法", value: "4" }
      ]
    },
    {
      id: "jimi-restaurant",
      name: "基米餐馆",
      desc: "川粤鲁苏浙闽湘徽、东北菜、家常小炒、烧烤、火锅、小吃、汤羹、饮品甜品，288 道菜随便点。要密码才能进。",
      tags: ["美食", "需要密码"],
      status: "online",
      icon: "🍚",
      lock: true,
      stats: [
        { label: "菜系", value: "15" },
        { label: "菜品", value: "288" }
      ]
    }
    /* 以后的新功能加在这里，例如：
    ,{
      id: "xxx",
      name: "功能名",
      desc: "一句话说明这个功能干什么。",
      tags: ["标签"],
      status: "coming",
      icon: "★"
    }
    */
  ];

  var STATUS_TEXT = { online: "已上线", beta: "测试中", coming: "计划中" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /** 当前页面属于哪个功能（靠路径第一段判断） */
  function currentId() {
    var p = location.pathname.replace(/^\/+|\/+$/g, "").split("/");
    // 自定义域名时 p[0] 是功能名；GitHub Pages 镜像时 p[0] 是仓库名，要往后找
    for (var i = 0; i < p.length; i++) {
      for (var j = 0; j < FEATURES.length; j++) {
        if (p[i] === FEATURES[j].id) return FEATURES[j].id;
      }
    }
    return "";
  }

  /** 生成指向某功能的链接（自动适配子目录部署） */
  function urlOf(f) {
    var base = document.documentElement.getAttribute("data-base") || "";
    return base + f.id + "/";
  }
  /** 首页的功能卡片 */
  function renderHome() {
    var host = document.getElementById("featureList");
    if (!host) return;
    host.innerHTML = FEATURES.map(function (f, i) {
      var dis = f.status === "coming";
      var stats = (f.stats || []).map(function (s) {
        return '<span class="badge">' + esc(s.label) + ' <b style="font-family:var(--mono)">' + esc(s.value) + "</b></span>";
      }).join("");
      var tags = (f.tags || []).map(function (t) {
        return '<span class="badge ftag">' + esc(t) + "</span>";
      }).join("");
      return '<a class="fcard reveal' + (dis ? " coming" : "") + '" data-d="' + ((i % 4) + 1) + '" ' +
        'href="' + esc(dis ? "javascript:void 0" : urlOf(f)) + '">' +
        '<div class="ficon">' + esc(f.icon || "★") + "</div>" +
        '<div class="fbody">' +
          '<div class="fhead">' +
            '<span class="fname">' + esc(f.name) + "</span>" +
            '<span class="badge st-' + esc(f.status) + '">' + STATUS_TEXT[f.status] + "</span>" +
          "</div>" +
          '<div class="fdesc">' + esc(f.desc) + "</div>" +
          '<div class="fbadges">' + tags + stats + "</div>" +
          (dis ? "" : '<div class="fgo">打开 →</div>') +
        "</div></a>";
    }).join("");
    if (window.SITE && window.SITE.reveal) window.SITE.reveal(host);
  }

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(function () {
    renderHome();
    var y = document.getElementById("siteCopy");
    if (y) y.textContent = SITE.copyright;
    var n = document.getElementById("s-feat");
    if (n) n.textContent = FEATURES.length;

    /* Service Worker：让第二次之后的访问直接从本地缓存打开。
       国内到 Cloudflare 的握手经常十几秒甚至超时，这一步收益最大。 */
    var localHost = location.hostname === "localhost" || location.hostname === "127.0.0.1";
    if ("serviceWorker" in navigator && (location.protocol === "https:" || localHost)) {
      var base = document.documentElement.getAttribute("data-base") || "./";
      navigator.serviceWorker.register(base + "sw.js", { scope: base })["catch"](function () {});
    }
  });

/* ============================================================
   质感增强（滚动进场 / 顶栏状态 / 键盘焦点）
   全站共用，功能页渲染完动态内容后调用 SITE.reveal() 即可。
   ============================================================ */
(function () {
  "use strict";

  var reduce = false;
  try {
    reduce = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {}

  var io = null;

  /** 让 .reveal 元素在进入视口时浮现；可重复调用（动态渲染后） */
  function reveal(root) {
    var list = (root || document).querySelectorAll(".reveal:not(.in)");
    if (!list.length) return;
    if (reduce || !("IntersectionObserver" in window)) {
      for (var i = 0; i < list.length; i++) list[i].classList.add("in");
      return;
    }
    if (!io) {
      io = new IntersectionObserver(function (ents) {
        for (var k = 0; k < ents.length; k++) {
          if (ents[k].isIntersecting) {
            ents[k].target.classList.add("in");
            io.unobserve(ents[k].target);
          }
        }
      }, { rootMargin: "0px 0px -6% 0px", threshold: 0.04 });
    }
    for (var j = 0; j < list.length; j++) io.observe(list[j]);
  }

  /** 顶栏：滚下去就收紧；底部那道彩线同时当滚动进度条 */
  function scrollState() {
    var ticking = false;
    function upd() {
      ticking = false;
      var doc = document.documentElement;
      var y = window.pageYOffset || doc.scrollTop || 0;
      document.body.classList.toggle("scrolled", y > 8);

      var max = doc.scrollHeight - window.innerHeight;
      if (max > 60) {
        document.body.classList.remove("no-prog");
        doc.style.setProperty("--prog", Math.min(1, y / max).toFixed(4));
      } else {
        document.body.classList.add("no-prog");
        doc.style.setProperty("--prog", "1");
      }
    }
    function onScroll() {
      if (!ticking) { ticking = true; requestAnimationFrame(upd); }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    upd();
  }

  function boot() {
    if (reduce) document.body.classList.add("no-prog");
    scrollState();
    reveal();
    /* 图片加载完高度会变，重新量一次进度 */
    window.addEventListener("load", function () {
      window.dispatchEvent(new Event("resize"));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  /* 注意：这里要挂到 SITE 对象上，不能用 window.SITE ——
     文件结尾还有一句 window.SITE = SITE，会把这里的赋值整个覆盖掉。 */
  SITE.reveal = reveal;
})();

  window.SITE = SITE;
  window.FEATURES = FEATURES;
})();
