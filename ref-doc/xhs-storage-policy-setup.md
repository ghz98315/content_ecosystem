# Supabase Storage 策略配置（修复 413 错误）

> 目的：让"新建书籍"上传 PDF 时，文件从浏览器**直接**传到 Supabase Storage，
> 绕过 Vercel API Route 的 4.5MB 限制。
>
> ⚠️ Storage 策略**不能**在 SQL Editor 里建（会报 `must be owner of table objects`），
> 必须走 Dashboard 的 Storage UI。

---

## 步骤 1 · 确认 artifacts 桶存在

1. [Supabase 控制台](https://supabase.com) → 选中你的项目
2. 左侧菜单点 **Storage**
3. 看有没有 `artifacts` 桶：
   - **有** → 跳到步骤 2
   - **没有** → 点 **New bucket**
     - Name: `artifacts`
     - Public bucket: **不勾选**（保持私有）
     - 点 **Save**

---

## 步骤 2 · 进入策略管理

1. 点开 `artifacts` 桶
2. 右上角点 **Policies** 按钮
3. 你会看到一个策略列表（第一次是空的）

---

## 步骤 3 · 创建「上传」策略（客户端上传 PDF）

点 **New policy** → 选 **For full customization**（完全自定义），逐项填：

| 字段 | 填写内容 |
|------|----------|
| **Policy name** | `xhs_anon_upload` |
| **Allowed operation** | 只勾 `INSERT` |
| **Target roles** | `anon` |
| **WITH CHECK expression** | `bucket_id = 'artifacts' AND name LIKE 'xhs/%'` |
| **USING expression** | 留空 |

点 **Save policy**

> 说明：只允许匿名用户往 `xhs/` 目录写文件，其它路径写不了，安全可控。

---

## 步骤 4 · 创建「下载」策略（服务端解析 PDF）

再点 **New policy** → 选 **For full customization**：

| 字段 | 填写内容 |
|------|----------|
| **Policy name** | `xhs_service_download` |
| **Allowed operation** | 只勾 `SELECT` |
| **Target roles** | `service_role` |
| **USING expression** | `bucket_id = 'artifacts'` |
| **WITH CHECK expression** | 留空 |

点 **Save policy**

> 说明：API Route 用 service_role key 下载 PDF 做文字解析。

---

## 步骤 5 · 验证

配置后策略列表应有两条：

```
✅ xhs_anon_upload        INSERT   anon
✅ xhs_service_download   SELECT   service_role
```

---

## 测试顺序

1. **文字模式**先测（不依赖 Storage，验证基础流程）
2. **PDF 模式**再测（验证大文件不再报 413）

### 报错对照

| 报错 | 原因 | 解决 |
|------|------|------|
| `上传失败：new row violates row-level security policy` | 上传策略没配 / 配错 | 检查步骤 3，`name LIKE 'xhs/%'` 别写错 |
| `下载 PDF 失败：Object not found` | 下载策略没配 | 检查步骤 4 |
| `服务器错误 413` | 代码没部署 / 还在走旧逻辑 | 确认 Vercel 部署了最新 commit `5ece063` |
| `Bucket not found` | artifacts 桶不存在 | 回步骤 1 建桶 |
