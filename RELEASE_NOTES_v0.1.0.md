# Release Notes - v0.1.0

## AI Memory Plugin for Claude Code v0.1.0

这是 `ai-memory-plugin` 的首个公开发布版本。

它的目标很简单：让 Claude Code 在本地逐步记住你的命令习惯、重复失败模式和可复用经验，同时保持克制，不打扰、不刷屏、不擅自替你做权限决策。

## Highlights

- 记录 Bash 命令执行结果到本地 `~/.ai-memory`
- 自动统计命令成功/失败次数
- 从重复失败中生成 lessons
- 从低风险高频成功命令中识别 habits
- 仅在高价值场景下进行温和提醒
- 默认静默运行，减少 Claude Code 对话噪音
- hook 异常 fail-open，降低对话被中断的风险
- 提供 memory summary 和 migration 工具
- 加入脱敏、路径裁剪和本地优先设计

## Why this release matters

Claude Code 很强，但每次会话都容易像“失忆重启”。这个插件尝试为它补上一层轻量、可控、本地化的长期记忆：

- 你踩过的坑，不必一直重复踩；
- 你稳定的习惯，不必每次重新证明；
- Claude 需要提醒时才提醒，不需要时就安静干活。

## Stability notes

首版重点优化了 hook 稳定性：

- `SessionStart` 默认静默
- `PostToolUse` 默认静默
- `PreToolUse` 仅高价值命中时提醒
- malformed JSON 或 hook 异常时 fail-open
- lessons 仅基于最近 `1000` 条事件重建
- 不自动注入 `permissionDecision: allow`

## Install

将仓库放置在本地并按 Claude Code 插件方式启用，确认存在：

```text
.claude-plugin/plugin.json
hooks/hooks.json
```

## Verify

```bash
python -m unittest discover -s tests -v
```

当前验证结果：`29` tests passing。

## Upgrade notes

如果你之前已经有 `~/.ai-memory` 数据，建议执行：

```bash
python scripts/migrate_memory.py --backup
```

## Known limitations

- 当前主要支持 Bash 命令记忆。
- 提醒阈值暂时写在代码中，后续可扩展为用户配置。
- 尚未提供独立 CLI 管理工具删除/编辑 lessons。

## Closing

这是一个小插件，但它试图解决一个很真实的问题：

> 让 AI 编程助手少一点“每次重新认识你”，多一点“我记得你上次怎么处理过”。
