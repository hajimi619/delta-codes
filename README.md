# 三角洲行动 · 改枪码库

把 GALI 的腾讯文档《[GALI的改枪码合集](https://docs.qq.com/sheet/DUmZJeER0dmNTSVRP)》里的改枪码
抓下来，做成一个能搜索、筛选、收藏、对比、一键复制的网页。

**收录 347 个改枪码 / 67 把枪 / 4 种玩法**（烽火地带 202 · 全面战场 86 · 烽火高操速T0 18 · 黑潮爆破 41）

![卡片视图](preview/01-cards.png)

## 功能

| 功能 | 说明 |
|---|---|
| 搜索 | 枪械名 / 改装名 / 改枪码全文匹配，空格分隔多个关键词是与关系 |
| 玩法筛选 | 全部 / 烽火地带 / 全面战场 / 烽火高操速T0 / 黑潮爆破 |
| 类型筛选 | 突击步枪 / 战斗步枪 / 冲锋枪 / 机枪 / 射手步枪 / 狙击枪 / 霰弹枪 / 手枪 / 其他 |
| 价格筛选 | 双滑块按改枪码价格过滤（从"32w性价比"这类改装名里解析），可勾选是否包含未标价 |
| 排序 | 按枪械 / 价格升序 / 价格降序 |
| 收藏 | 卡片右上角 ★，存在浏览器本地；顶部会出现「★ 收藏」页签，可「只看收藏」 |
| 对比 | 卡片右上角 ⇄，最多同时选 3 套，底部对比栏 → 并排表格（自动标出价格最高/最低） |
| 按枪械分组 | 一键切换分组视图，每把枪可「复制全部」（多行文本，一行一个码，方便整批粘贴） |
| 分享链接 | 「复制当前链接」把搜索词、筛选、分组状态、甚至正在打开的对比都编进 URL |
| 一键复制 | 每个码单独复制，兼容 `file://` 打开（自动降级到 execCommand） |

![按枪械分组](preview/02-groups.png)
![方案对比](preview/03-compare.png)

## 本地打开

直接双击 `docs/index.html`，纯静态、不需要服务器、不联网。

## 目录

```
delta-codes/
├─ docs/                     ← GitHub Pages 发布目录
│  ├─ index.html             网页本体（界面 + 交互）
│  ├─ data.js                由 build_site.py 生成的数据包（window.DELTA_DATA）
│  └─ .nojekyll
├─ data/
│  └─ codes.json             抓取结果（原始记录，含来源 tab / 行列号）
├─ scripts/
│  ├─ fetch_codes.py         从腾讯文档抓取并解析 → data/codes.json
│  └─ build_site.py          data/codes.json → docs/data.js（清洗 + 补 id/价格）
├─ preview/                  截图
└─ .github/workflows/
   └─ refresh-codes.yml      在 GitHub 上手动触发一次数据刷新（可选定时）
```

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
> 想用自己的域名，在 Pages 里填 Custom domain 即可。

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
- 原表版权归 GALI 所有，本站只是便于检索的镜像；改枪码失效请以原文档为准。
