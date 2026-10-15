# Coppermind 中文维基搬运项目

目标：从英文 Coppermind 站抓取 wikitext → 翻译成中文 → 通过 MediaWiki API 写回同名的中文站（红铜智库）。

## 两个站点

| 站 | 域 | API 端点 | 鉴权 |
|---|---|---|---|
| 英文站 | https://coppermind.net | `https://coppermind.net/w/api.php` | 无需 key（用 cloudscraper 绕 Cloudflare） |
| 中文站 | https://coppermind.huijiwiki.com | `https://coppermind.huijiwiki.com/api.php` | 需 `X-authkey` 头（值在 `.env`） |

站点名：中文站 = 「红铜智库中文维基」，MediaWiki 1.38.4；英文站 = The Coppermind Wiki。
中文站首页 wiki 名：`首页`（mainpage），revid 16588。

## 关键结论（截至现在）

- **读取英文站 wikitext**：已跑通。例：`Allik_Neverfar` 用
  `GET /w/api.php?action=query&prop=revisions&rvprop=content&titles=<标题>` 拿到 7830 字符完整 wikitext（含 `{{character}}`/`{{quote}}`/`{{date}}`/`{{book ref}}`/`[[内链]]`）。
- **读取中文站**：已跑通，需 `X-authkey` 头走 `api.php`（否则 Cloudflare 403）。
- **中文站写入（edit/创建）**：❌ **尚未打通**。当前 authkey 只给读取权限（匿名、rights=0），拿到的 CSRF token 是无效 `+\`。
  - 写操作需要**已登录用户的 CSRF token**（`action=edit` 前先 `meta=tokens&type=csrf`）。
  - 中文站 `action=login` API 可用（login token 能取到，未被拦截），需要 **bot 账号（用户+密码）** 才能登录拿有效 token。
- Cloudflare：英文站用 cloudscraper（TLS 指纹伪装）可过；中文站**必须**带 `X-authkey`，否则 API 层也被 403 拦。

## 技术方案

- 用 `cloudscraper`（python，已在环境安装）→ 实际走标准 MediaWiki API，无需额外 skill/插件。
- 已装过 `huiji-wiki-bot` skill（`/root/lianz/.agents/skills/huiji-wiki-bot`），是对同一套 API 的封装，可选用（需 env：`HUIJI_API`/`HUIJI_WIKI`、`HUIJI_API_KEY`、可选 `HUIJI_BOT_USER/PASS`）。

## 下一步（待办）

1. ✅ 英→中读取链路已通
2. ⬜ 拿到中文站 bot 账号（用户+密码）→ 登录 → 拿有效 CSRF token → `action=edit` 写入
3. ⬜ 翻译 `Allik_Neverfar` 词条并贴回中文站

## 凭据

API key 在 `.env`（已 gitignore，勿提交）。账号类凭据后续也放 `.env`。
