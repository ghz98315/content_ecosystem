# 自定义域名配置指南

目标：将 `content.socra.cn` 绑定到 Vercel 前端项目

---

## 第一步：腾讯云 DNS 添加解析

1. 登录腾讯云控制台：https://console.cloud.tencent.com/cns
2. 点击 **DNS解析 DNSPod** → 找到 `socra.cn` → 点击**解析**
3. 点击右上角 **添加记录**，填写：

| 字段     | 填写内容                  |
|----------|---------------------------|
| 主机记录 | `content`                 |
| 记录类型 | `CNAME`                   |
| 线路类型 | 默认                      |
| 记录值   | `cname.vercel-dns.com`    |
| TTL      | `600`                     |

4. 点击**保存**

---

## 第二步：Vercel 绑定域名

1. 打开 https://vercel.com/dashboard
2. 进入项目 → 顶部 **Settings** → 左侧 **Domains**
3. 输入框填入 `content.socra.cn` → 点击 **Add**
4. Vercel 自动检测 CNAME，显示 ✅ Valid Configuration 即成功

---

## 第三步：验证生效

DNS 通常 5~30 分钟生效。验证方式：

```powershell
nslookup content.socra.cn
```

返回指向 Vercel 的地址即成功。

浏览器直接打开 https://content.socra.cn，Vercel 会自动签发 HTTPS 证书。

---

## 常见问题

| 问题 | 原因 | 处理 |
|------|------|------|
| Vercel 提示 Invalid Configuration | DNS 未生效 | 等待 30 分钟后刷新 |
| 页面打开显示 404 | 域名绑定了但 Vercel 项目没选对 | 检查绑定的是正确的 project |
| HTTPS 证书错误 | 证书还在签发中 | 等待 5 分钟再试 |

---

## 后续优化（可选）

如国内访问仍然慢，可将域名 DNS 迁移到 Cloudflare，开启代理模式（橙色云朵），利用 Cloudflare 边缘节点加速。
