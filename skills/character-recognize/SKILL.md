---
name: character-recognize
description: 识别本地动漫插画中的角色与作品，或通过 SauceNAO、Trace.moe 反查 Pixiv、画师和动画出处。用于用户提供本地图片路径并询问角色、作品、原图、画师或动画截图来源时。
---

# 插画识别

使用 `character-recognize` MCP 处理用户明确提供的本地图片路径。

## 工具选择

- 验证刚安装的候选版本时调用无参数的 `verify_installation`；成功取得 `status=ok` 后结束 attached child，让父 turn 正常结束并由 Core 完成切换。此工具不用于普通识图请求。
- 只询问角色或作品时调用 `recognize_character`。
- 只询问原图、Pixiv、画师或动画出处时调用 `reverse_search`。
- 同时需要角色与来源，或用户笼统要求“识别这张图”时调用 `recognize_illustration`。
- 不要自行猜测、改写或构造图片路径；路径不可读时向用户说明。

## 结果边界

- `characters`、`matches` 和 `final_verdict` 是置信度不低于 0.7 的命中。
- `ambiguous` 只表示疑似候选，不得表述为已确认。
- `final_verdict` 为 `null` 时明确说明证据不足，不要用模型常识补全角色或来源。
- `errors` 非空时说明对应服务调用失败，同时继续使用其他服务已经返回的结果。
- 原图和出处只使用 `source_links` 中的链接。数组为空时说明未反查到来源，不得伪造 Pixiv ID、链接或占位 URL。
- 多角色结果按工具返回顺序展示，保留视觉证据和置信度。

## 凭据

不要请求用户在对话中粘贴 API Key。视觉模型和 SauceNAO 密钥只应写入 Akashic plugin-data 的 `config.local.toml`，或由宿主进程环境变量提供。
