# Akashic 插画识别插件

在 Akashic 中识别动漫插画里的角色和作品，并反查 Pixiv 原图、画师或动画截图出处。

## 使用前准备

必须准备：

- 一个支持图片输入、兼容 OpenAI Chat Completions 接口的视觉模型 API Key。
- 默认使用阿里云百炼 DashScope 的 `qwen-vl-max`。

可选准备：

- SauceNAO API Key。没有 Key 也能匿名反查，但额度更低。
- Trace.moe 不需要配置 Key。

## 安装

在 Akashic 仓库中执行：

```bash
.venv/bin/python main.py plugin-install \
  --source https://github.com/lfegg/character-recognize-mcp.git \
  --marketplace github
```

安装完成后，终端会显示插件数据目录，通常类似：

```text
<Akashic 工作目录>/plugin-data/character-recognize-github/
```

## 配置

在插件数据目录中创建 `config.local.toml`：

```toml
request_timeout_seconds = 30
rate_limit_enabled = true

[vision]
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "<你的 DASHSCOPE_API_KEY>"
model = "qwen-vl-max"

[saucenao]
api_key = "<你的 SAUCENAO_API_KEY>"
```

`vision.api_key` 必须填写。没有 SauceNAO Key 时，删除 `[saucenao]` 两行即可使用匿名模式。

限制私密配置文件的访问权限：

```bash
chmod 600 /path/to/plugin-data/character-recognize-github/config.local.toml
```

不要把 API Key 写入仓库、命令行参数或聊天消息。

配置完成后检查插件：

```bash
.venv/bin/python main.py plugin-doctor character-recognize@github
```

检查通过后，重新打开一个 Akashic 会话，让新会话加载插件。

## 怎么用

先确保图片位于运行 Akashic 的电脑上。支持 JPEG、PNG、WebP 和 GIF，单张图片不能超过 20 MiB。

在 Akashic 对话中直接提供图片的绝对路径，例如：

```text
识别这张插画里的角色和出处：/Users/me/Pictures/example.png
```

也可以只查询其中一项：

```text
这张图里是谁：/Users/me/Pictures/example.png
```

```text
帮我找这张图的 Pixiv 原图和画师：/Users/me/Pictures/example.png
```

识别结果会区分“已命中”和“疑似候选”。置信度低于 0.7 的结果不会被当作确认答案；没有可靠来源时，插件不会编造 Pixiv 链接。

## 使用其他视觉模型

插件也支持其他 OpenAI compatible 图片模型。以 OpenCode Go 的 `mimo-v2.5` 为例，将 `[vision]` 替换为服务商提供的配置：

```toml
[vision]
base_url = "<服务商提供的 compatible API 地址>"
api_key = "<你的 API Key>"
model = "mimo-v2.5"
```

接口地址必须使用 HTTPS，并且模型必须支持图片输入。

开发者需要查看 MCP 工具、返回结构、环境变量和测试方式时，请阅读 [开发文档](docs/development.md)。
