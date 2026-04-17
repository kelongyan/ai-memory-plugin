# AI Memory Plugin for Claude Code

<div align="center">

# AI Memory Plugin

### 让 Claude Code 不只是“会写代码”，还会“记得你是怎么写代码的”

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white)](#-安装方式)
[![Tests](https://img.shields.io/badge/Tests-29%20Passing-2ea44f?style=for-the-badge)](#-当前测试状态)
[![Hooks](https://img.shields.io/badge/Claude%20Code-Hooks%20Plugin-7c3aed?style=for-the-badge)](#️-工作原理)
[![Mode](https://img.shields.io/badge/Reminder-High%20Value%20Only-ff9800?style=for-the-badge)](#-插件能做什么)

一个为 Claude Code 增加本地命令记忆能力的轻量插件，强调低干扰、可追溯和可演进的使用体验。

</div>

---

## ✨ 项目亮点

- 🧠 **记忆命令行为**：记录 Bash 命令成功与失败结果，沉淀长期使用模式
- 🔎 **总结重复问题**：将重复失败归纳为 `lessons`，而不是保留零散报错
- 🤫 **默认静默运行**：避免不必要的输出干扰 Claude Code 正常交互
- 💡 **高价值才提醒**：仅在强信号场景下输出提示
- 🔐 **本地优先 + 脱敏处理**：降低敏感信息暴露风险
- 🧪 **测试覆盖完整**：核心逻辑、hook 稳定性、提醒策略均有测试保护

> 本项目的核心目标是为 Claude Code 增加一层可控的本地记忆能力，用于减少重复试错并提升连续使用体验。

---

## 📚 目录

- [✨ 项目亮点](#-项目亮点)
- [🧠 创作动机](#-创作动机)
- [🎯 设计目的](#-设计目的)
- [🚀 插件能做什么](#-插件能做什么)
- [🪄 效果示意](#-效果示意)
- [🏗️ 项目结构](#️-项目结构)
- [⚙️ 工作原理](#️-工作原理)
- [💾 本地存储说明](#-本地存储说明)
- [🔐 安全与隐私设计](#-安全与隐私设计)
- [📦 安装方式](#-安装方式)
- [📌 使用方式详解](#-使用方式详解)
- [🧪 开发与测试](#-开发与测试)
- [🧩 输出逻辑说明](#-输出逻辑说明)
- [🛠️ 故障排查](#️-故障排查)
- [🧪 当前测试状态](#-当前测试状态)
- [🗺️ 未来可扩展方向](#️-未来可扩展方向)
- [🤝 适合谁使用](#-适合谁使用)
- [📄 License](#-license)

---

## 🧠 创作动机

在日常使用 Claude Code 时，常会遇到几个真实问题：

1. 同样的命令错误会重复发生，例如环境没激活、依赖没安装、PATH 没配好。
2. Claude 每次会话都像“失忆重启”，很难持续积累用户的命令习惯。
3. 高频成功命令和典型失败模式，本身就值得沉淀，以减少重复试错。
4. 如果提示过于频繁或缺乏约束，实际体验反而会下降。

因此，本项目采用以下设计原则：

- 记录真实行为，而不是推测用户意图；
- 提炼可复用经验，而不是堆积原始日志；
- 默认静默运行，尽量减少干扰；
- 仅在高价值场景下提醒，避免增加上下文噪音。

该项目试图在“完全没有记忆能力”和“过度打扰用户的自动提醒”之间，建立一个更克制、更工程化的平衡点。

---

## 🎯 设计目的

本项目主要解决以下问题：

### 1. 让 Claude Code 逐渐理解你的命令习惯

例如：

- 你经常在某个项目里执行 `git status`
- 你总是先跑 `pytest`
- 你习惯用 `python -m pytest` 而不是直接 `pytest`

插件会把这些低风险、重复成功的命令模式积累下来，形成“习惯候选”。

### 2. 让重复错误不再白白重复

例如某条命令曾多次因以下原因失败：

- `command not found`
- `ModuleNotFoundError`
- `permission denied`

插件会总结成 lesson，而不是只保留零散 stderr。

### 3. 在关键时刻给出高价值提醒

当前版本已优化为“温和提醒模式”：

- 默认静默
- 仅在强信号出现时提示
- 不自动修改权限
- 不频繁向 Claude 对话流插入消息

这样既保留了记忆价值，也尽量避免影响 Claude Code 的正常交互。

---

## 🚀 插件能做什么

### 已实现能力

- 记录 Bash 命令的执行结果到本地 `~/.ai-memory`
- 统计命令成功/失败次数
- 识别重复失败的错误签名
- 自动归纳 lessons（经验教训）
- 识别低风险高频成功命令，生成 habits / allow candidates
- 在 `PreToolUse` 阶段为高价值风险或高价值习惯提供提醒
- 提供内存数据迁移脚本
- 提供本地 memory summary 汇总脚本

### 当前提醒策略

插件目前仅在以下情况下提示：

#### 高价值失败提醒
满足任一条件：

- `project` 级别 lesson
- `failure_count >= 3`
- `confidence >= 0.8`

#### 高价值习惯提醒
满足：

- `success_count >= 5`

除上述情况外，插件保持静默。

---

## 🪄 效果示意

### 场景 A：重复失败时的温和提醒

当你多次执行类似命令并命中高价值失败模式后，`PreToolUse` 会在执行前输出提醒：

```text
ai-memory 提醒：该命令与历史失败模式相似。
- command: `npm test`
- scope: project
- repeated_failures: 3
- advice: `npm test` 之前多次因命令不可用失败。先检查工具是否已安装，或当前 shell/PATH 是否正确。
```

### 场景 B：稳定习惯被识别

当某个低风险命令在项目中稳定成功多次后：

```text
ai-memory 提醒：该命令命中历史成功习惯。
- command: `git status`
- scope: project
- success_count: 5
- suggested_permission: allow
- cwd: c:/work/demo
- note: 仅供参考，不会自动修改权限设置。
```

### 场景 C：默认保持静默

在大多数情况下，插件不会主动输出内容：

```text
SessionStart  -> 静默
PostToolUse   -> 静默
PreToolUse    -> 仅高价值命中时提醒
```

这种设计用于控制上下文噪音，并尽量降低对 Claude Code 主流程的干扰。

---

## 🏗️ 项目结构

```text
ai-memory-plugin/
├─ .claude-plugin/
│  └─ plugin.json              # Claude Code 插件元信息
├─ hooks/
│  ├─ hooks.json               # Hook 注册配置
│  └─ scripts/
│     ├─ session_start.py      # 会话开始时初始化（当前默认静默）
│     ├─ pre_tool_use.py       # 执行前提醒高价值风险/习惯
│     └─ post_tool_use.py      # 执行后记录结果并更新记忆
├─ scripts/
│  ├─ sanitize.py              # 脱敏、路径规整、错误签名归一化
│  ├─ memory_store.py          # 数据读写、统计、候选习惯生成
│  ├─ lesson_engine.py         # lessons 重建与匹配逻辑
│  ├─ memory_summary.py        # 查看 memory 摘要
│  └─ migrate_memory.py        # 迁移旧数据
├─ skills/
│  └─ ai-memory-assistant/
│     └─ SKILL.md              # 面向记忆分析的技能说明
└─ tests/
   ├─ test_memory_plugin.py    # 主测试集
   └─ fixtures/                # Hook 输入输出样例
```

---

## ⚙️ 工作原理

插件主要通过 Claude Code 的 Hook 机制工作：

### 1. `SessionStart`

会话开始时初始化 `~/.ai-memory` 目录及默认文件：

- `events.jsonl`
- `lessons.json`
- `preferences.json`
- `stats.json`

当前策略：

- 初始化但不打扰用户
- 默认静默输出
- 异常 fail-open，不中断会话

### 2. `PostToolUse`

当 Bash 命令执行结束后：

- 记录事件到 `events.jsonl`
- 更新命令统计和错误签名统计
- 对低风险高频成功命令生成候选习惯
- 对重复失败模式重建 lessons

当前策略：

- 只负责记忆，不主动插入对话
- 默认静默输出
- 为稳定性考虑，仅基于最近 `1000` 条事件重建 lessons

### 3. `PreToolUse`

当 Claude Code 准备执行 Bash 命令时：

- 检查该命令是否命中高价值失败 lesson
- 检查是否命中高价值使用习惯
- 仅在高价值场景下输出提醒

当前策略：

- 不自动放权
- 不默认打断
- 只在值得提示时输出信息

---

## 💾 本地存储说明

插件会将数据保存在用户目录下：

```text
~/.ai-memory/
```

包含以下文件：

### `events.jsonl`
原始事件流，按行存 JSON，记录：

- 时间戳
- 命令内容
- 命令前缀
- cwd
- 成功/失败
- return code
- 脱敏后的 stdout/stderr
- error signature

### `lessons.json`
从重复失败中提炼出的经验集合。

### `preferences.json`
保存习惯候选、工具偏好、阈值等配置。

### `stats.json`
汇总命令统计和错误签名统计。

---

## 🔐 安全与隐私设计

本插件是本地优先设计，重点关注两件事：

1. 尽量有用
2. 不要泄露秘密

### 已实现的安全处理

- 对 token / password / api key / bearer 等常见敏感内容做脱敏
- 对路径做规整与裁剪
- 对错误信息做签名归一化，减少噪音
- 不会自动上传 `~/.ai-memory` 内容
- 不会自动修改 Claude Code 权限策略

### 你仍然应该注意

- 不要把真实 `~/.ai-memory` 数据直接提交到 GitHub
- 不要把包含敏感命令输出的本地文件当成示例公开
- 如果你修改了脱敏规则，请重新审视日志内容是否安全

---

## 📦 安装方式

### 环境要求

- Windows / macOS / Linux
- Python 3.13+（项目当前在 Python 3.13 环境下测试通过）
- Claude Code 支持插件 Hook 机制

### 安装步骤

1. 将本项目放到本地目录，例如：

```bash
C:\Users\Administrator\ai-memory-plugin
```

2. 确认插件描述文件存在：

```text
.claude-plugin/plugin.json
```

3. 确认 Hook 配置存在：

```text
hooks/hooks.json
```

4. 按 Claude Code 的插件加载方式安装/启用该插件。

当前插件元信息如下：

```json
{
  "name": "ai-memory-plugin",
  "version": "0.1.0",
  "description": "Claude Code plugin that records command outcomes into ~/.ai-memory and surfaces reusable lessons before repeated mistakes.",
  "hooks": "./hooks/hooks.json"
}
```

---

## 📌 使用方式详解

### 场景一：你反复执行一个总失败的命令

例如你在某个项目里多次执行：

```bash
npm test
```

如果它连续多次因为 `jest` 不存在而失败，插件会逐渐归纳出一条 lesson，例如：

- 该命令前缀：`npm test`
- 错误签名：`command not found: jest`
- 作用域：全局或项目级
- 建议：先检查工具是否安装或 PATH 是否正确

之后当 Claude 再次准备执行相似命令时，如果该 lesson 达到“高价值提醒阈值”，就会在执行前提示。

### 场景二：你有稳定的命令习惯

例如你在某个项目中频繁且成功地执行：

```bash
git status
```

插件会将其视为低风险高频成功命令，并在达到高价值阈值后识别为“稳定习惯候选”。

注意：

- 这只是提醒，不是自动授权
- 这只是记忆，不是替你做决定

### 场景三：查看本地记忆摘要

```bash
python scripts/memory_summary.py --pretty
```

你可以看到：

- Top commands
- Top error signatures
- Lessons
- Project habits
- Global habits

如果看到这些内容，说明插件已经开始积累有效记忆数据。

### 场景四：迁移旧数据

```bash
python scripts/migrate_memory.py --backup
```

适合在你调整数据结构、升级插件版本之后做一次安全迁移。

---

## 🧪 开发与测试

### 运行测试

```bash
python -m unittest discover -s tests -v
```

### 使用 fixture 调试 hook

```bash
python tests/run_fixture.py pre_tool_use.py pre_tool_use.json
python tests/run_fixture.py post_tool_use.py post_tool_use_success.json
python tests/run_fixture.py post_tool_use.py post_tool_use_failure.json
```

### 查看 memory 摘要

```bash
python scripts/memory_summary.py
```

输出 JSON：

```bash
python scripts/memory_summary.py --json
```

输出更适合人眼阅读的摘要：

```bash
python scripts/memory_summary.py --pretty
```

只看某些部分：

```bash
python scripts/memory_summary.py --pretty --only overview,lessons
```

限制数量：

```bash
python scripts/memory_summary.py --json --limit 5
```

### 迁移旧 memory 数据

```bash
python scripts/migrate_memory.py
```

仅预演不落盘：

```bash
python scripts/migrate_memory.py --dry-run
```

迁移前备份：

```bash
python scripts/migrate_memory.py --backup
```

---

## 🧩 输出逻辑说明

### 默认行为

- `SessionStart`：静默
- `PostToolUse`：静默
- `PreToolUse`：只在高价值命中时提醒

### 为什么这样设计？

因为记忆类插件既要提供价值，也要避免成为新的噪音来源。

当前版本优先保证低干扰和稳定性，在此基础上逐步增强提醒能力。

---

## 🛠️ 故障排查

### 1. 为什么我看不到提醒？

可能原因：

- 当前命令没有命中 lesson 或 habit
- 命中了，但强度不足，未达到高价值阈值
- 该命令不属于支持分析的低风险习惯类命令
- `~/.ai-memory` 里尚未积累足够数据

### 2. 为什么我以前会遇到 Claude 对话被截断？

历史上常见原因包括：

- hook 每次执行都输出系统消息，噪音过多
- hook 异常时没有 fail-open 保护
- 每次命令后全量扫描历史，导致超时或不稳定

当前版本已做以下优化：

- hooks 默认静默
- hooks 异常 fail-open
- lessons 重建只处理最近 1000 条事件
- 不再自动注入 `permissionDecision: allow`

### 3. 如何确认插件在工作？

可直接查看：

```bash
python scripts/memory_summary.py --pretty
```

如果你看到命令统计、错误签名、lessons 或 habits，说明插件已经正常积累记忆。

---

## 🧪 当前测试状态

本项目当前已通过完整单元测试集，覆盖内容包括：

- 路径与敏感信息脱敏
- 错误签名归一化
- lessons 生成与匹配
- habits 候选生成
- hook 静默策略
- hook 异常 fail-open
- 高价值提醒模式
- memory summary / migrate 脚本

运行命令：

```bash
python -m unittest discover -s tests -v
```

当前状态：

- `29` 个测试通过
- 核心 hook 行为已验证
- 文档更新后验证通过

---

## 🗺️ 未来可扩展方向

如果后续继续演进，这个插件还可以扩展为：

- 更细粒度的 per-project 偏好学习
- 用户可配置的提醒阈值
- 更丰富的 lesson 去重与合并策略
- CLI 管理工具（查看/删除/重建 memory）
- 可视化统计面板
- 对更多工具类型的记忆支持，而不只是 Bash

---

## 🤝 适合谁使用

这个项目特别适合：

- 重度使用 Claude Code 的开发者
- 希望减少重复踩坑的人
- 想把“临时经验”沉淀成“长期协作记忆”的人
- 希望工具具备学习能力，但保持克制输出的人

---

## 📄 License

本项目采用 `MIT` License。

版权所有者信息：`KeLong Yan <zhaxideler@gmail.com>`

这意味着你可以相对自由地使用、修改、分发和二次开发本项目，只需保留原始版权与许可声明。对于希望快速开源、方便传播和低门槛复用的工具型项目来说，MIT 是一个非常务实的选择。

---

## ❤️ 最后的话

本项目的目标并不是改变 Claude Code 的工作方式，而是为其补充一层可控、本地化、可持续积累的使用记忆。

如果你关注以下问题：

- 减少重复试错
- 沉淀项目级使用习惯
- 在不增加噪音的前提下提供有效提醒

那么这个项目可能会对你的工作流有所帮助。
