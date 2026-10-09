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
  function homeUrl() {
    return document.documentElement.getAttribute("data-base") || "./";
  }

  /** 顶部功能切换导航 */
  function renderNav() {
    var host = document.getElementById("siteNav");
    if (!host) return;
    var cur = currentId();
    var parts = [];
    for (var i = 0; i < FEATURES.length; i++) {
      var f = FEATURES[i];
      var on = f.id === cur;
      var dis = f.status === "coming" && !on;
      parts.push(
        '<a href="' + esc(dis ? "javascript:void 0" : urlOf(f)) + '"' +
        (on ? ' class="on"' : "") +
        (dis ? ' style="opacity:.45;cursor:default"' : "") +
        ">" + esc(f.name) + (dis ? " ·" + STATUS_TEXT[f.status] : "") + "</a>"
      );
    }
    parts.unshift('<a href="' + esc(homeUrl()) + '"' + (cur ? "" : ' class="on"') + ">⌂ 首页</a>");
    parts.push('<span class="sep"></span>');
    parts.push('<span style="font-size:12.5px;color:var(--dim2)">' + FEATURES.length + " 个功能</span>");
    host.innerHTML = parts.join("");
  }

  /** 首页的功能卡片 */
  function renderHome() {
    var host = document.getElementById("featureList");
    if (!host) return;
    host.innerHTML = FEATURES.map(function (f) {
      var dis = f.status === "coming";
      var stats = (f.stats || []).map(function (s) {
        return '<span class="badge">' + esc(s.label) + ' <b style="font-family:var(--mono)">' + esc(s.value) + "</b></span>";
      }).join("");
      var tags = (f.tags || []).map(function (t) {
        return '<span class="badge ftag">' + esc(t) + "</span>";
      }).join("");
      return '<a class="fcard' + (dis ? " coming" : "") + '" href="' + esc(dis ? "javascript:void 0" : urlOf(f)) + '">' +
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
  }

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(function () {
    renderNav();
    renderHome();
    var y = document.getElementById("siteCopy");
    if (y) y.textContent = SITE.copyright;
    var n = document.getElementById("s-feat");
    if (n) n.textContent = FEATURES.length;
  });

  window.SITE = SITE;
  window.FEATURES = FEATURES;
})();
