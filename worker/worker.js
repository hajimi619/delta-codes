/**
 * 哈基米工具箱 · 域名跳转 Worker
 *
 * Cloudflare 已经**停用**：不再托管站点（Pages 自定义域名已摘掉）、
 * 不再提供接口（D1 绑定已去掉）、数据也不再落在 Cloudflare。
 *
 * 这里只剩一个「路牌」：访问 hajimiovo.top / www.hajimiovo.top 的任何路径，
 * 301 跳到国内的腾讯云服务器，这样别人记的旧域名不会打不开。
 *
 * 等 ICP 备案通过后，把域名直接解析到服务器，这个 Worker 就可以彻底删掉了。
 */
"use strict";

const TARGET = "http://119.45.171.242:8080";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const to = TARGET + url.pathname + url.search;
    return new Response(null, {
      status: 301,
      headers: {
        "Location": to,
        "Cache-Control": "no-store",
      },
    });
  },
};
