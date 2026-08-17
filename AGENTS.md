# Repository Agent Rules

本文件适用于整个 `character-recognize-mcp` 仓库。

## Git 操作边界

- Agent 可以读取、编辑、测试、查看 diff、暂存并创建本地 commit。
- 用户说“实现”“更新”“修复”或“提交”时，默认授权边界止于本地 commit，不包含任何远端操作；下文“空白仓库初始化”是唯一例外。
- `git push`、force push、远端分支创建或删除、创建或修改 PR、合并或关闭 PR、创建 tag 或 release、修改 GitHub 仓库设置，默认全部由用户执行。
- 只有用户在当前消息中明确要求 Agent 执行具体远端操作时，Agent 才能执行该项操作。之前任务中的授权不得沿用到后续任务。
- 未获得明确授权时，Agent 在本地 commit 后必须停止，并报告当前分支、commit SHA、验证结果和工作区状态。
- Agent 可以按用户要求提供 PR title 和 description，但不得因此自行创建或更新 PR。
- 不得为了“完成流程”而推断 push、PR 或 merge 已获授权。

## 空白仓库初始化

- 开始任务前先只读检查本地提交、分支和远端引用。只有本地没有任何 commit，并且远端也没有任何分支时，才视为空白仓库；远端不可访问或状态不明确时不得按空白仓库处理。
- 空白仓库必须先创建并切换到 `main`，只提交仓库基础文件，例如 `.gitignore`、`AGENTS.md` 和占位 `README.md`。初始化提交不得包含本次任务的功能实现。
- 初始化 commit 使用 `chore:初始化仓库`，随后只允许执行一次 `git push -u origin main`，并确认远端 HEAD 指向 `main`。这是空白仓库流程中唯一无需用户在当前消息再次授权的远端操作。
- `main` 初始化并推送成功后，必须从 `main` 创建 `codex/` 前缀的任务分支；本次任务的实现、测试和后续 commit 全部在任务分支进行。
- origin 不存在、远端不是空白仓库、初始化 push 失败或远端默认分支不是 `main` 时，停止自动远端操作并向用户报告，不得扩大权限或改写远端状态。

## 分支与提交

- 除空白仓库的最小初始化 commit 外，不直接在受保护的 `main` 上提交；默认从最新 `main` 创建 `codex/` 前缀的任务分支。
- commit 使用约定式提交格式，并使用中文描述，例如 `feat:添加插画角色识别工具`。
- 未获明确授权时，不得改写已经发布的分支历史。
- 发现工作区存在用户改动时必须保留，不得回退、覆盖或混入无关提交。

## 仓库与凭据边界

- `/Users/lfegg/Documents/GitHub/akashic-agent` 与 `/Users/lfegg/Documents/GitHub/bangumi-mcp` 只允许按任务需要只读参考，不得修改、暂存或提交其中任何文件。
- 视觉模型 API Key 与 SauceNAO API Key 只能来自环境变量或 Akashic plugin-data 的私密配置，不得写入 Git、日志、命令参数或工具结果。
