# 开发文档

## 插件结构

`character-recognize-mcp` 是 Akashic Plugin API v2 插件。`plugin.py` 注册 Skill 根目录和 stdio MCP server，`mcp/run_mcp.py` 从 `AKA_PLUGIN_DATA_DIR` 定位私密配置并启动 FastMCP。

核心模块：

- `mcp/src/client.py`：compatible-mode 视觉模型、SauceNAO 和 Trace.moe 客户端。
- `mcp/src/config.py`：plugin-data 私密配置与环境变量加载。
- `mcp/src/service.py`：模型 JSON 容错、置信度分流、反查规范化和结果融合。
- `mcp/src/server.py`：FastMCP 工具注册。

## MCP 工具

- `recognize_character(image_path)`：识别角色和作品。
- `reverse_search(image_path)`：通过 SauceNAO 和 Trace.moe 反查来源。
- `recognize_illustration(image_path)`：并行执行视觉识别和两个来源反查，再执行融合裁决。

工具返回 JSON 字符串。所有顶层结果都包含 `source_links`；没有可靠来源时为 `[]`。置信度低于 `0.7` 的项目进入 `ambiguous`，不进入命中结果。综合结果包含：

- `visual`：视觉模型的角色识别证据。
- `reverse_search`：SauceNAO 与 Trace.moe 候选。
- `final_verdict`：融合后的高置信度裁决，证据不足时为 `null`。
- `ambiguous`：低置信度候选。
- `source_links`：经过验证和去重的来源链接。

来源链接依次优先展示 Pixiv 作品页、SauceNAO 外部来源或 Danbooru 条目、Trace.moe 动画截图。融合模型给出的 Pixiv ID 只有在 SauceNAO 候选中真实出现时才会保留。

`recognize_illustration` 的第一阶段使用独立线程并行调用视觉模型、SauceNAO 和 Trace.moe。任何一个调用失败都只写入 `errors`，不会取消其他调用；视觉模型失败时跳过依赖视觉证据的融合步骤，保留并返回两个反查服务已经取得的结果。`reverse_search` 也会并行调用两个反查服务并允许部分成功。

## 私密配置

运行时读取 Akashic plugin-data 下的 `config.local.toml`。密钥也可以由宿主进程环境变量提供，且环境变量优先：

```text
CHARACTER_RECOGNIZE_VISION_API_KEY
CHARACTER_RECOGNIZE_SAUCENAO_API_KEY
```

SauceNAO 限流默认开启，同一 MCP 进程内两次请求的起始时间至少间隔 8 秒。

## 开发验证

```bash
python -m pip install -r mcp/requirements.txt -r requirements-dev.txt
pytest
PYTHONPATH=/path/to/plugin-contracts \
  python -m akashic_plugin_contracts check plugin.py
```

测试使用假的视觉模型和反查响应，不访问真实 API，也不需要任何密钥。
