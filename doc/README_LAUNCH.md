# 漫画翻译器启动脚本使用说明

## 📋 脚本说明

### Windows 批处理脚本 (.bat)

#### 1. `launch_win.bat` - 标准启动
**功能**: 普通启动,不检查更新
**使用场景**: 日常使用,快速启动
**用法**:
```bash
# 双击运行,或命令行:
launch_win.bat

# 使用 Qt 界面:
launch_win.bat --ui qt

# 查看详细日志:
launch_win.bat --verbose
```

#### 2. `launch_win_with_autoupdate.bat` - 自动更新启动(推荐)
**功能**: 
- 启动前自动检查并更新到最新版本
- **自动下载Git**: 首次运行时会提示下载Git(如果未安装)
- 一键完成所有设置

**使用场景**: 
- 想要保持最新版本
- 需要获取最新功能和修复
- **新用户推荐**: 无需手动安装Git

**用法**:
```bash
# 双击运行:
launch_win_with_autoupdate.bat

# 首次运行会询问:
# [1] 自动下载便携版 Git (约50MB, 推荐)
# [2] 跳过,继续启动
# [3] 退出,手动安装 Git
```

#### 3. `launch_qt.bat` - Qt界面启动
**功能**: 使用 PyQt6 界面启动
**使用场景**: 偏好 Qt 界面的用户
**用法**:
```bash
launch_qt.bat
```

#### 4. ~~`install_dependencies.bat` - 依赖安装~~(可选)
**功能**: 安装项目依赖包
**使用场景**: 首次使用或重新安装依赖
**注意**: `launch_win_with_autoupdate.bat` 会自动检查依赖，通常不需要单独运行此脚本
**用法**:
```bash
# 双击运行,会提示选择:
# [1] GPU 版本 - 需要 NVIDIA 显卡
# [2] CPU 版本 - 通用版本
install_dependencies.bat
```

---

### Python 启动脚本 (launch.py)

#### 基本用法

```bash
# 使用 Python 3.12
py -3.12 launch.py

# 或直接使用
python launch.py
```

#### 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--update` | 启动前检查更新 | `python launch.py --update` |
| `--ui <qt\|tk>` | 选择UI框架 | `python launch.py --ui qt` |
| `--cli` | 命令行模式 | `python launch.py --cli` |
| `--frozen` | 跳过依赖检查 | `python launch.py --frozen` |
| `--reinstall-torch` | 重新安装PyTorch | `python launch.py --reinstall-torch` |
| `--requirements <文件>` | 指定依赖文件 | `python launch.py --requirements requirements_cpu.txt` |
| `--verbose` | 详细日志 | `python launch.py --verbose` |

---

## 🚀 快速开始

### 1. 首次安装

**最简单方式 (推荐):**
```bash
# 双击运行 (会自动下载Git、安装依赖):
launch_win_with_autoupdate.bat
```

**手动安装方式:**
```bash
# 如果需要手动安装依赖:
install_dependencies.bat
```

### 2. 启动应用

```bash
# 推荐: 自动更新版本 (首次会提示下载Git)
launch_win_with_autoupdate.bat

# 或使用标准版本:
launch_win.bat

# 或使用 Python 直接启动:
py -3.12 launch.py
```

---

## 🔧 高级功能

### 自动更新系统

**工作原理**:
1. 使用 Git 获取远程最新代码
2. 对比本地和远程的 commit hash
3. 如有更新,自动执行 `git pull`
4. 重启应用加载新代码

**要求**:
- 必须安装 Git
- 项目目录必须是 Git 仓库
- 有网络连接

**使用**:
```bash
# 方式一: 使用自动更新脚本
launch_win_with_autoupdate.bat

# 方式二: 命令行参数
python launch.py --update
```

### GPU 自动检测

启动脚本会自动检测你的 GPU 类型:
- **NVIDIA**: 安装 CUDA 版本的 PyTorch
- **AMD**: 安装 ROCm 版本的 PyTorch
- **Intel/CPU**: 安装 CPU 版本的 PyTorch

### 多UI支持

```bash
# CustomTkinter UI (默认)
python launch.py --ui tk

# PyQt6 UI
python launch.py --ui qt
```

---

## 📝 环境变量

可以通过环境变量自定义行为:

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `GIT` | Git 可执行文件路径 | `set GIT=C:\Git\bin\git.exe` |
| `TORCH_COMMAND` | 自定义 PyTorch 安装命令 | `set TORCH_COMMAND=pip install torch...` |
| `INDEX_URL` | PyPI 镜像源 | `set INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` |

---

## ❓ 常见问题

### Q: 提示找不到 Python 3.12?
**A**: 安装 Python 3.12+, 下载地址: https://www.python.org/downloads/
确保安装时勾选 "Add Python to PATH"

### Q: 自动更新失败?
**A**: 
1. 检查是否安装了 Git
2. 确认网络连接正常
3. 手动更新: `git pull origin main`

### Q: PyTorch 安装失败?
**A**:
1. 确认显卡类型是否支持
2. 尝试使用 CPU 版本: `python launch.py --requirements requirements_cpu.txt`
3. 手动安装: 访问 https://pytorch.org/

### Q: 如何切换 GPU/CPU 版本?
**A**:
```bash
# 重新安装依赖并指定版本
python launch.py --requirements requirements_gpu.txt --reinstall-torch
# 或
python launch.py --requirements requirements_cpu.txt --reinstall-torch
```

---

## 🔄 更新日志

### v1.7.6
- ✅ 添加完整的启动脚本系统
- ✅ 支持自动更新
- ✅ 自动检测 GPU 类型
- ✅ 支持多种 UI 框架
- ✅ Python 3.12 支持

---

## 📞 技术支持

- GitHub Issues: https://github.com/hgmzhn/manga-translator-ui/issues
- 项目主页: https://github.com/hgmzhn/manga-translator-ui

