# 三角洲行动 · 改枪码库

> **🌐 在线访问：<https://hajimiovo.top/>**
> 手机、电脑直接打开，无需登录，所有人都能新增 / 标记失效改枪码。
>
> 镜像：<https://hajimi619.github.io/delta-codes/> · 仓库：<https://github.com/hajimi619/delta-codes>
> 接口：<https://api.hajimiovo.top/api/changes>

把一份公开的腾讯文档《三角洲行动改枪码合集》里的改枪码
抓下来，做成一个能搜索、筛选、收藏、对比、一键复制的网页。

**收录 347 个改枪码 / 67 把枪 / 4 种玩法**（烽火地带 202 · 全面战场 86 · 烽火高操速T0 18 · 黑潮爆破 41）


## 功能

**没有搜索框，全部靠分类浏览。** 结构是两级：

1. **首屏按枪械类型分块**（步枪 / 冲锋枪 / 机枪 / 射手步枪 / 狙击步枪 / 霰弹枪 / 手枪 / 其他），每块下面是这类的枪械卡片
2. **点任意一张枪械卡片**，进去看这把枪的每一个价位方案

| 功能 | 说明 |
|---|---|
| 玩法分类 | 顶部标签：全部 / 烽火地带 / 全面战场 / 烽火高操速T0 / 黑潮爆破（数字是**枪械把数**） |
| 类型分类 | 第二排标签：**步枪（突击 + 战斗合并）25** / 冲锋枪 11 / 机枪 4 / 射手步枪 8 / **狙击步枪 6** / 霰弹枪 4 / 手枪 7 / 其他 2；不选时按类型**分块显示**，选了就只看这一类 |
| 枪械卡片 | 一张卡一把枪：**枪械图** + 类型 / 套数 / 价格区间 / 玩法 / 方案名预览，右上角 ★ 整把收藏 |
| 方案详情 | 点卡片进入，按价格从低到高列出每个价位：改装名 + 价格 + 玩法 + 改枪码 + 复制/收藏/对比 |
| 价格筛选 | 双滑块按价格过滤（价格从"32w性价比"这类改装名里解析），可勾选是否包含未标价 |
| 排序 | 按枪械名 / 最低价从低到高 / 最高价从高到低 / 方案数量 |
| 收藏 | 枪械卡片上 ★ 整把收藏，详情里每套可单独收藏；存在浏览器本地，顶部会出现「★ 收藏」页签 |
| 对比 | 详情页每套 ⇄，最多同时选 3 套，底部对比栏 → 并排表格（自动标出价格最高/最低） |
| 复制全部 | 详情页「复制全部 N 个码」，多行文本一行一个码，整批粘进游戏；**数量跟随当前筛选** |
| 分享链接 | 「复制当前链接」把玩法、类型、价格、排序、**正在看的那把枪**都编进 URL，打开就是同一视图 |
| 返回/前进 | 进入和退出枪械详情走浏览器历史，手机返回手势和浏览器后退键都能用 |

![按类型分块的首屏](preview/01-cards.png)
![点进枪械后的价位方案](preview/02-groups.png)
![方案对比](preview/03-compare.png)

## 本地打开

直接双击 `docs/index.html`，纯静态、不需要服务器、不联网。

## 目录

```
delta-codes/
├─ docs/                     ← 发布目录（Cloudflare Pages + GitHub Pages 共用）
│  ├─ index.html             网页本体（界面 + 交互）
│  ├─ data.js                由 build_site.py 生成的数据包（window.DELTA_DATA）
│  ├─ img/guns/*.webp        68 张枪械图
│  └─ .nojekyll
├─ data/
│  ├─ codes.json             抓取结果（基础数据，含来源 tab / 行列号）
│  └─ gun-images.json        枪名 → 图片文件名 的映射
├─ assets/
│  └─ gun-screenshots/       游戏图鉴截图（枪械图的来源，13 张）
├─ worker/                   ← 在线编辑后端（Cloudflare Worker + D1）
│  ├─ worker.js              接口代码
│  ├─ schema.sql             数据库结构
│  └─ README.md              部署指南（点点点 + 粘贴，约 5 分钟）
├─ config.json               配置：apiBase 填 Worker 地址；留空 = 只读模式
├─ scripts/
│  ├─ fetch_codes.py         从腾讯文档抓取并解析 → data/codes.json
│  ├─ extract_gun_images.py  从图鉴截图裁出每把枪 → docs/img/guns/*.webp
│  ├─ build_site.py          data/*.json → docs/data.js（清洗 + 补 id/价格/图片）
│  ├─ build_singlefile.py    打包成单文件 dist/delta-codes.html（图片内联）
│  ├─ deploy_github.py       纯 REST API 部署到 GitHub Pages（不需要 git）
│  └─ deploy_pages.ps1       部署 docs/ 到 Cloudflare Pages（走 wrangler）
├─ preview/                  截图
└─ .github/workflows/
   └─ refresh-codes.yml      在 GitHub 上手动触发一次数据刷新（可选定时）
```

## 枪械图是怎么来的

原始素材是 13 张游戏内**枪械图鉴列表**截图（放在 `assets/gun-screenshots/`）。
`scripts/extract_gun_images.py` 会自动把每把枪裁成独立小图：

1. 图鉴每行固定高约 **89px**，行内**左上角是白色枪名文字**、下方才是枪身
2. 先用「左上角近白文字」定位每一行，行距用等差数列拟合（比按高度均分稳）
3. 再取标题下方的窗口，用**边缘强度**找枪的轮廓外接框——
   背景是平滑渐变几乎没有边缘，枪有清晰轮廓，所以这个判据比"和背景色做差"可靠得多
4. 图鉴里被**选中**的那一项有一圈近白色高亮边框，会按
   「贯穿整行/整列 + 亮度 > 200」识别出来，连同两侧的抗锯齿一起剔除

输出 68 张 WebP（每把枪约 1.5 KB，**合计 105 KB**），页面用 CSS 径向遮罩把图片边缘
淡出，融进卡片背景。

重新生成：

```powershell
& $py scripts\extract_gun_images.py
& $py scripts\build_site.py
```

## 在线编辑

站点**已经开启**在线编辑，后端是 **Cloudflare Worker + D1**（免费额度足够），
接口地址 <https://api.hajimiovo.top>，写进 `config.json`：

```json
{ "apiBase": "https://api.hajimiovo.top" }
```

`apiBase` 留空即回到只读模式。部署步骤见 [worker/README.md](worker/README.md)。

页面上的入口：**「+ 新增改枪码」**（筛选栏右侧）和每条的 **「标记失效」**（详情页 ⊘）。

**接口：**

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/changes` | 拉取全部改动（新增 + 失效标记） |
| POST | `/api/add` | 新增一个改枪码 |
| POST | `/api/flag` | 标记失效 / 恢复 |

**防滥用：** 同一个码不能重复提交 · 每 IP 每小时最多 30 次写操作 ·
枪械名 / 名字 / 备注都有长度上限 · CORS 只放行自有域名和 GitHub Pages。

**设计上刻意做了两层保护：**

1. **删除 = 标记失效**，不是真删。码还在，只是折叠 + 显示"已失效"，任何人可点 ↺ 恢复。
2. **基础 347 条不在数据库里**，而是躺在仓库的 `data/codes.json`（有 git 历史）。
   数据库只存"新增"和"失效标记"，所以**就算数据库被清空，基础数据一条不少**，
   重跑一次 `fetch_codes.py` 就恢复。

新增时会要求填 **新建人名字**，列表上会显示"由 XXX 添加"。

![开启编辑后的方案列表：失效的码被划掉并折叠，网友新增的带标记](preview/04-edit.png)
![新增改枪码表单，含必填的"新建人名字"](preview/05-add.png)

## 更新数据

本地（推荐）：

```powershell
$py = "C:\Users\哈基米.OBITO\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
cd D:\APP\dswork\delta-codes
& $py scripts\fetch_codes.py --out data\codes.json
& $py scripts\build_site.py
```

刷新浏览器即可。仓库里还带了 `.github/workflows/refresh-codes.yml`：
推到 GitHub 后，在 Actions 里点「Run workflow」也能刷新（会自己 commit 回仓库，
Pages 随后自动重新发布）；想每天自动跑就把 `schedule` 的注释打开。

## 部署

站点同时发布到两个地方，内容一样：

| 目标 | 地址 | 部署方式 | 说明 |
|---|---|---|---|
| **Cloudflare Pages** | <https://hajimiovo.top/> | `scripts/deploy_pages.ps1` | **主站**。国内可直连（约 1–3 秒） |
| GitHub Pages | <https://hajimi619.github.io/delta-codes/> | `scripts/deploy_github.py` | 镜像 / 备份 |

```powershell
cd D:\APP\dswork\delta-codes
& pwsh scripts\deploy_pages.ps1      # Cloudflare（token 放在 ..\.cf-token）
& $py scripts\deploy_github.py --token-file ..\.gh-token --repo delta-codes
```

两个脚本都会跳过内容没变的文件。

### 域名与解析

- `hajimiovo.top` / `www.hajimiovo.top` → CNAME → `delta-codes.pages.dev`（Cloudflare 代理）
- `api.hajimiovo.top` → Cloudflare Worker `delta-codes-api`（自定义域名）
- DNS 托管在 Cloudflare（NS：`mckenzie` / `robert`.ns.cloudflare.com），**不需要备案**

> 为什么不用 Worker 自带的 `*.workers.dev`：那个域名在国内被 DNS 污染，
> 普通用户**完全连不上**，接口会一直失败。换成自己的域名后国内实测可以直连。

## 发布到 GitHub Pages

1. 在 GitHub 建一个空仓库（public）。
2. 在本目录执行：

   ```bash
   git init
   git add .
   git commit -m "三角洲改枪码库"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```

3. 仓库 **Settings → Pages**：
   - Source 选 **Deploy from a branch**
   - Branch 选 **main**，目录选 **/docs**
   - Save
4. 等 1 分钟左右，访问 `https://<你的用户名>.github.io/<仓库名>/`。

> 因为发布目录就叫 `docs`，不需要任何构建步骤，Pages 直接读这个文件夹。

## 数据是怎么拿到的

腾讯文档没有开放 API。它的表格数据以 **zlib 压缩的 protobuf** 内嵌在页面接口里：

1. `GET https://docs.qq.com/dop-api/opendoc?tab=<tabId>&id=<docId>&outformat=1...`
2. 返回 JSON 的 `clientVars.collab_client_vars.initialAttributedText.text[0]`
   里，`block_datas[*].related_sheet` 是 base64 的 zlib 数据块
3. base64 解码 → `zlib.decompress` → protobuf
4. 关键结构 `sheet.r0.f19[0]`：
   - `f3` = 表信息（表 id、行数、列数）
   - `f5` = 单元格文本表（共享字符串）
   - `f6` = 单元格：`{f1: 行, f2: 列, f3: {f2: {f1: 文本索引}, f4: {f1: 样式索引}}}`
5. **只有含文本的单元格**，其 `f3` 会多出 `f1`/`f2` 两个字段，`f3.f2.f1` 就是文本索引。

`scripts/fetch_codes.py` 自带一个通用 protobuf wire-format 解析器（不需要 `.proto` 文件），
所以腾讯调整字段顺序也不会立刻失效。

## 几个实现上的取舍

- **枪械名从改枪码本身解析**（`MDR突击步枪-烽火地带-6L6J...` → `MDR突击步枪`），
  因为原表的枪械名是跨行合并单元格，逐行读会错位。
- **记录 id 用 `玩法|改枪码`**：有 5 个码同时出现在烽火和 T0 两个表里，光用码会撞。
- 大战场那个 tab 同一份码在 3 组列里重复了 3 遍（原表注明"哪列方便用哪列都是一样的"），已按码去重。
- 原表有 151 条没写价格，所以价格筛选默认勾选「包含未标价」，避免一拉滑块东西全没了。
- 原表里有些格子把枪械名当改装名（"沙鹰"），生成数据时已剔除。

## 已知限制

- 数据是**快照**：腾讯文档更新后需要重新跑一次脚本（或点一次 Action）。
- 抓取用了固定分片参数（`endrow=60&block_end_row=255`）。如果某个 tab 突然抓不到数据，
  多半是腾讯改了分片参数，调 `scripts/fetch_codes.py` 里 `fetch_tab()` 的 query 即可。
- 改枪码随游戏版本变动，遇到失效换一套或稍后再试即可。
