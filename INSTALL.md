# AI Memory Plugin 安装指南

本插件支持两种安装模式:**本地开发模式**和 **GitHub 发布模式**。

---

## 🔧 模式 1: 本地开发模式 (推荐用于插件开发)

### 适用场景
- 你正在开发或调试插件
- 需要快速迭代和测试
- 修改代码后立即生效

### 安装步骤

1. **克隆仓库到本地**
```bash
git clone https://github.com/kelongyan/ai-memory-plugin.git
cd ai-memory-plugin
```

2. **配置 Claude Code settings.json**

编辑 `~/.claude/settings.json`,添加以下配置:

```json
{
  "extraKnownMarketplaces": {
    "ai-memory-marketplace": {
      "source": {
        "source": "directory",
        "path": "C:\\Users\\Administrator\\ai-memory-plugin"
      }
    }
  },
  "enabledPlugins": {
    "ai-memory-plugin@ai-memory-marketplace": true
  }
}
```

**注意**: 将路径替换为你的实际插件目录路径。

3. **重启 Claude Code**

### 优点
✅ 修改代码立即生效,无需重新安装  
✅ 便于调试和测试  
✅ 可以直接查看和修改源码  
✅ 支持 Git 版本控制

### 缺点
⚠️ 需要手动管理更新  
⚠️ 换机器需要重新配置

---

## 🌐 模式 2: GitHub 发布模式 (推荐用于生产使用)

### 适用场景
- 你想使用稳定版本
- 需要自动更新功能
- 多台机器使用

### 安装步骤

1. **配置 Claude Code settings.json**

编辑 `~/.claude/settings.json`,添加以下配置:

```json
{
  "extraKnownMarketplaces": {
    "ai-memory-marketplace": {
      "source": {
        "source": "github",
        "repo": "kelongyan/ai-memory-plugin"
      }
    }
  },
  "enabledPlugins": {
    "ai-memory-plugin@ai-memory-marketplace": true
  }
}
```

2. **重启 Claude Code**

Claude Code 会自动从 GitHub 下载插件到:
```
~/.claude/plugins/cache/ai-memory-marketplace/ai-memory-plugin/0.1.0/
```

### 优点
✅ 自动检查和安装更新  
✅ 标准化安装位置  
✅ 可移植性好  
✅ 支持版本管理

### 缺点
⚠️ 修改代码需要 push 到 GitHub 才能生效  
⚠️ 不适合频繁开发调试

---

## 🔄 模式切换

### 从本地模式切换到 GitHub 模式

1. 确保本地更改已提交并推送到 GitHub
```bash
git add -A
git commit -m "Your changes"
git push origin main
```

2. 修改 `~/.claude/settings.json`:
```json
{
  "extraKnownMarketplaces": {
    "ai-memory-marketplace": {
      "source": {
        "source": "github",  // 改为 github
        "repo": "kelongyan/ai-memory-plugin"  // 添加 repo
      }
    }
  }
}
```

3. 重启 Claude Code

### 从 GitHub 模式切换到本地模式

1. 克隆仓库到本地(如果还没有)
```bash
git clone https://github.com/kelongyan/ai-memory-plugin.git
```

2. 修改 `~/.claude/settings.json`:
```json
{
  "extraKnownMarketplaces": {
    "ai-memory-marketplace": {
      "source": {
        "source": "directory",  // 改为 directory
        "path": "C:\\Users\\Administrator\\ai-memory-plugin"  // 添加本地路径
      }
    }
  }
}
```

3. 重启 Claude Code

---

## 📋 验证安装

安装完成后,运行以下命令验证插件是否正常工作:

```bash
# 查看 memory 摘要
python scripts/memory_summary.py --pretty

# 运行测试
python -m unittest discover -s tests -v
```

如果看到命令统计、lessons 或 habits,说明插件已正常工作。

---

## 🔍 故障排查

### 插件未加载

1. 检查 `~/.claude/settings.json` 配置是否正确
2. 确认 `enabledPlugins` 中包含 `"ai-memory-plugin@ai-memory-marketplace": true`
3. 重启 Claude Code

### 本地模式路径错误

确保路径使用正确的格式:
- Windows: `"C:\\Users\\Administrator\\ai-memory-plugin"`
- macOS/Linux: `"/Users/username/ai-memory-plugin"`

### GitHub 模式下载失败

1. 检查网络连接
2. 确认 GitHub 仓库地址正确
3. 查看 Claude Code 日志

---

## 📚 更多信息

- [README.md](README.md) - 项目概述和功能说明
- [CLAUDE.md](CLAUDE.md) - 开发指南
- [GitHub 仓库](https://github.com/kelongyan/ai-memory-plugin)
