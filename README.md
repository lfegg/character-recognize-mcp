# character-recognize-mcp

Akashic Plugin API v2 插件。它通过兼容 OpenAI Chat Completions 的视觉模型识别动漫插画中的角色和作品，并结合 SauceNAO、Trace.moe 反查 Pixiv、画师及动画截图出处。

## MCP 工具

- `recognize_character(image_path)`：只做角色与作品识别。
- `reverse_search(image_path)`：调用 SauceNAO 与 Trace.moe 反查来源。
- `recognize_illustration(image_path)`：完成视觉识别、来源反查与最终融合裁决。

所有工具都返回 JSON 字符串。置信度低于 `0.7` 的条目只进入 `ambiguous`，不会作为命中；`source_links` 始终存在，无法确认来源时为 `[]`。

## 安装

Akashic 只安装 Git 已提交快照。从 Akashic 仓库执行：

```bash
.venv/bin/python main.py plugin-install \
  --source https://github.com/lfegg/character-recognize-mcp.git \
  --marketplace github
```

安装输出会给出插件数据目录，默认类似：

```text
<workspace>/plugin-data/character-recognize-github/
```

## 配置

在插件数据目录创建权限为 `0600` 的 `config.local.toml`。默认视觉模型为 DashScope compatible-mode 的 `qwen-vl-max`：

```toml
request_timeout_seconds = 30
rate_limit_enabled = true

[vision]
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "<DASHSCOPE_API_KEY>"
model = "qwen-vl-max"

[saucenao]
api_key = "<SAUCENAO_API_KEY>"
```

SauceNAO Key 可以省略，此时使用匿名模式。`rate_limit_enabled = true` 时插件保证同一 MCP 进程内两次 SauceNAO 请求间隔不少于 8 秒，建议保持开启。

密钥也可以通过 Akashic 宿主进程环境变量提供，环境变量优先于配置文件：

```text
CHARACTER_RECOGNIZE_VISION_API_KEY
CHARACTER_RECOGNIZE_SAUCENAO_API_KEY
```

不要把密钥放进仓库、日志、命令行参数或聊天消息。配置完成后可运行：

```bash
.venv/bin/python main.py plugin-doctor character-recognize@github
```

### OpenCode Go / mimo-v2.5

视觉客户端使用标准 compatible-mode 消息格式。切换到 OpenCode Go 时，只需在私密配置中替换服务提供方给出的 HTTPS `base_url`、API Key 与模型名：

```toml
[vision]
base_url = "<OPENCODE_GO_COMPATIBLE_BASE_URL>"
api_key = "<OPENCODE_GO_API_KEY>"
model = "mimo-v2.5"
```

## 调用方式

工具参数必须是 Akashic 主机可读取的本地图片绝对路径，支持 JPEG、PNG、WebP 和 GIF，单文件不超过 20 MiB。例如：

```json
{"image_path":"/absolute/path/to/illustration.png"}
```

综合识别结果包含 `visual`、`reverse_search`、`final_verdict`、`ambiguous` 与 `source_links`。来源链接按 Pixiv 原图页、SauceNAO 外部来源（含 Danbooru）、Trace.moe 动画截图的优先级排列，不生成占位链接。

## 开发验证

```bash
python -m pip install -r mcp/requirements.txt -r requirements-dev.txt
pytest
PYTHONPATH=/path/to/plugin-contracts \
  python -m akashic_plugin_contracts check plugin.py
```

测试使用假的视觉与反查响应，不调用真实 API，也不需要任何密钥。
