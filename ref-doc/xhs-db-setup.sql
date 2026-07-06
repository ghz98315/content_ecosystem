-- XHS Content Engine — 数据库初始化 SQL
-- 在 Supabase SQL Editor 执行以下语句

-- 1. 知识库：书籍/电子资料
CREATE TABLE IF NOT EXISTS xhs_books (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title        TEXT NOT NULL,
  brand_name   TEXT NOT NULL DEFAULT '大厂工程爸',
  raw_text     TEXT,
  file_url     TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 2. 选题矩阵
CREATE TABLE IF NOT EXISTS xhs_topics (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      UUID REFERENCES xhs_books(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  pain_point   TEXT,
  logic        TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 3. 文案草稿（含卡片数据）
CREATE TABLE IF NOT EXISTS xhs_drafts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id     UUID REFERENCES xhs_topics(id) ON DELETE SET NULL,
  style        TEXT,
  body         TEXT,
  comments     JSONB,
  pages        JSONB,
  summary      TEXT,
  cta          TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 4. RLS（可选，如需多用户隔离则开启）
-- ALTER TABLE xhs_books ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE xhs_topics ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE xhs_drafts ENABLE ROW LEVEL SECURITY;
