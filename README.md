# xfqtrace-skills（技能仓库）

用于私有 xfQTrace kit 的 `xfq` CLI 和智能体技能。

## 安装

```bash
pipx install xfqtrace-skills
```

## 首次使用

```bash
# xfqtrace-kit zip 和密码请进入 x1a0f3n9 知识星球自取，公开 pip 包不内置私有 kit
xfq init ./xfqtrace-kit-<version>.zip -p <password>
# Windows 如果不想把 kit 放 C 盘，可以指定:
# xfq init ./xfqtrace-kit-<version>.zip -p <password> --dir D:\xfqtrace
xfq doctor --serial <device-serial>
xfq run test --serial <device-serial>                # 默认 xfinject，com.shopee.vn 指纹函数
```

可选：

```bash
xfq set auto-update-check off
xfq run test --serial <device-serial> --inject-backend frida-server
```

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `xfq paths` | 查看 kit 安装目录、配置文件路径 |
| `xfq doctor --serial <device>` | 只检查环境，不做清理 |
| `xfq doctor --serial <device> --install-kpm --kpm-superkey <key>` | 检查并按需加载 kit/bin/xfvmahide.kpm |
| `xfq run test --serial <device> --dry-run` | 用当前真实 kit 检查将执行的命令 |
| `xfq clean --traces -y` | 清理本机 kit/examples 下的 trace/logcat 产物 |
| `xfq clean --all-versions -y` | 删除非当前版本的旧 kit |
| `xfq update` | 更新 xfqtrace-skills 包并刷新技能 |
| `xfq skill install --target both --force` | 安装/刷新技能 |

## 安装目录

kit 安装在用户数据目录。Linux/macOS 默认走 XDG 风格目录，Windows 默认走 `%LOCALAPPDATA%`。具体以 `xfq paths` 实际输出为准。

```bash
$HOME/.local/share/xfqtrace/versions/<version>/   # Linux/macOS
%LOCALAPPDATA%/xfqtrace/versions/<version>/        # Windows
```

Windows 想改到 D 盘：

```powershell
xfq init .\xfqtrace-kit-<version>.zip -p <password> --dir D:\xfqtrace
```

技能目录不受 `--dir` 影响，仍然是用户目录下的 `.codex/skills` / `.claude/skills`。

## 智能体技能

```bash
xfq skill install --target both
xfq skill status
```

## 查看日志

`xfq run` 会把本轮产物放到：

```text
<kit>/examples/<package>/xfqtrace_logs/<N>/
```

控制台会打印 `Session dir` 和最终 `Output`。重点看：

```bash
sed -n '1,200p' <output>/logcat.txt
cat <output>/crash_summary.txt
ls <output>/*.log.lz4
```

实时看设备日志：

```bash
adb -s <device-serial> logcat -v threadtime -s xfQTrace
```

## 更新

`xfq` 默认会检查 `xfqtrace-skills` 更新。检测到 CLI / skill 有新版本时，会提示输入 `y/n`：

- 输入 `y`：自动更新本地 pip 包，并刷新 Codex / Claude 已安装技能。
- 输入 `n`：跳过本次更新。

也可以手动执行：

```bash
xfq update
xfq update -y
```

这个公开仓库不包含私有 kit、APK、辅助脚本或密码；kit/libxfqtrace 更新需要重新去知识星球下载 zip，然后再 `xfq init <new-kit.zip> -p <password> --force`。

## kit/bin 工具检查

`xfq init` 会显示 `kit/bin` 里的工具状态；`xfq doctor --json` 里也有 `bundle.bundled_tools`：

- 必须：`libxfqtrace.so`
- 建议：`lz4`、`lz4.exe`、`pidcat`、`pidcat.exe`、`7z`、`7z.exe`
- 可选：`xfvmahide.kpm`

`xj3` / frida-server 不打包进 kit。选择 `--inject-backend frida-server` 时，推荐设备侧 server 为 `16.5.7`，Python 侧推荐 `frida==16.2.1`、`frida-tools==12.0.0`。

## 样本反馈

如果一个样本跑不通，按最小材料格式反馈。尽量包含：

```text
apk: <package / version / source>
json: <recipe.json or CONFIG snippet>
target: libxxx.so!0xoffset
sig: <optional JNI/RegisterNatives name/signature>
steps: <trigger steps + whether clear data/login needed>
backend: <xfinject | frida-server>
logs: <logcat/crash/trace dir>
```

`sig` 是 Java native 方法签名，例如 `(Landroid/content/Context;Ljava/lang/String;)Ljava/lang/String;`。
