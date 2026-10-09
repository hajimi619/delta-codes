-- 三角洲改枪码库 · D1 数据库结构
-- 用法：Cloudflare 控制台 → Storage & Databases → D1 → 你的库 → Console → 粘贴执行

CREATE TABLE IF NOT EXISTS changes (
  id          TEXT PRIMARY KEY,   -- uuid
  type        TEXT NOT NULL,      -- 'add'（新增） | 'flag'（失效标记）
  target_id   TEXT,               -- flag 时：被标记的记录 id
  status      TEXT,               -- flag 时：'invalid' | 'valid'
  gun         TEXT,               -- add 时：枪械名
  build       TEXT,               -- add 时：改装名 / 价位
  tab         TEXT,               -- add 时：玩法
  mode        TEXT,               -- add 时：游戏内模式
  code        TEXT,               -- add 时：改枪码
  author      TEXT,               -- add 时：新建人名字
  created_at  TEXT NOT NULL,
  ip_hash     TEXT                -- 提交者 IP 的哈希，仅用于限流
);

CREATE INDEX IF NOT EXISTS idx_changes_created ON changes (created_at);
CREATE INDEX IF NOT EXISTS idx_changes_ip      ON changes (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_changes_code    ON changes (code);
CREATE INDEX IF NOT EXISTS idx_changes_target  ON changes (type, target_id);
