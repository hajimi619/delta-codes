# 在线编辑后端（Cloudflare Worker + D1）部署指南

这个目录是"所有人都能新增 / 标记失效改枪码"功能的服务端。
**跟着做大概 5 分钟，全程点点点 + 粘贴，不用装任何东西、不用命令行。**

免费额度足够：Workers 每天 10 万次请求，D1 免费 5GB 存储 + 每天 500 万次读。

---

## 第 1 步：建数据库

1. 打开 <https://dash.cloudflare.com> 并登录（没有账号就注册一个，免费）
2. 左侧菜单找 **Storage & Databases** → **D1 SQL Database**
3. 点 **Create** / **Create database**
4. 名字填 **`delta-codes`** → 点 **Create**
5. 进入这个数据库，切到 **Console** 标签页
6. 把本目录 `schema.sql` 的**全部内容**复制粘贴进去 → 点 **Execute**

   看到成功提示就行。这一步是建存改动的那张表。

---

## 第 2 步：建 Worker

1. 左侧菜单 → **Workers & Pages** → **Create** → 选 **Workers** → **Start with Hello World** → **Deploy**
2. 名字填 **`delta-codes-api`** → **Deploy**
3. 部署完成后点 **Edit code**（编辑代码）
4. 把编辑器里的示例代码**全部删掉**，粘贴本目录 `worker.js` 的**全部内容**
5. 点右上角 **Deploy**

---

## 第 3 步：把数据库接上 Worker（关键，别漏）

1. 回到这个 Worker 的页面 → **Settings** → **Bindings**（有的界面叫 "Bindings" 或 "变量和绑定"）
2. 点 **Add binding** → 选 **D1 Database**
3. **Variable name** 必须填 **`DB`**（大写，一个字母都不能差）
4. **D1 database** 下拉里选第 1 步建的 `delta-codes`
5. 保存 / **Deploy**

> 漏了这步的话，接口会报 `env.DB is undefined`。

---

## 第 4 步：自测 + 把地址发我

Worker 页面顶部会显示它的地址，形如：

```
https://delta-codes-api.你的子域.workers.dev
```

**在浏览器里打开这个地址**，应该看到：

```json
{"ok":true,"service":"delta-codes-api"}
```

看到这行就说明后端活了。**把这个地址发给我**，我改一行配置重新部署，前端的「+ 新增改枪码」和「标记失效」按钮就会出现。

---

## 接口说明（部署好后可直接验证）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/changes` | 拉取全部改动 |
| POST | `/api/add` | 新增，body：`{gun, build, tab, code, author}` |
| POST | `/api/flag` | 标记失效/恢复，body：`{target_id, status:"invalid"\|"valid"}` |

想确认写进去了，可以在 D1 的 Console 里跑：

```sql
SELECT type, gun, build, code, author, created_at FROM changes ORDER BY created_at DESC LIMIT 20;
```

---

## 防滥用（已内置）

- 每个 IP **每小时最多 30 次**写操作
- 字段长度限制：枪械名 24、改装名 40、名字 16、码 32
- 改枪码必须匹配 `8–32 位字母数字`
- 同一条码不能重复提交
- 同一 IP 对同一条码只保留最新标记

## 数据安全

- 基础 347 条数据**不在数据库里**，而是躺在仓库的 `data/codes.json`（有完整 git 历史）。
  D1 里只存"新增"和"失效标记"。所以**就算数据库被清空，基础数据也一条不少**，
  重新跑一次抓取脚本就恢复。
- 要更保险，可以在 D1 Console 里定期导出：
  `wrangler d1 export` 或直接在上面那条 SELECT 里复制结果。

## 想清空所有网友改动

在 D1 Console 里执行：

```sql
DELETE FROM changes;
```

站点立刻回到 347 条基础数据的状态。
