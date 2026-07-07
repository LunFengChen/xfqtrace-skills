---
name: xfqtrace-workflow
description: 当智能体需要帮助用户安装 xfQTrace kit、定位 kit 目录、用 kit 里的 全自动化trace.py 跑 trace、配置 recipe.json/CONFIG/hook_format/filter/exclude、选择 xfinject/frida-server 后端、查看 logcat/trace 产物、诊断 App 自身问题/环境不干净/Frida 检测/trace 不触发时使用。公开 pip 包不包含私有 kit/APK/密码，kit 需要进 x1a0f3n9 知识星球获取。
---

# xfQTrace 智能体工作流

核心原则：`xfq` 只是辅助工具；智能体自动 trace 时直接调用 kit 里的 `全自动化trace.py`，不要把 `xfq run` 当主路径。

## 1. 先确认 kit 和环境

如果用户还没有 kit：

```bash
# kit zip 和密码请进入 x1a0f3n9 知识星球获取；公开 pip 包不内置私有 kit
xfq init ./xfqtrace-kit-<version>.zip -p <password>
xfq doctor --serial <serial>
xfq paths
```

Windows 不想放默认 C 盘时：

```powershell
xfq init .\xfqtrace-kit-<version>.zip -p <password> --dir D:\xfqtrace
```

默认安装位置：

| 平台 | kit 位置 |
| --- | --- |
| Linux | `~/.local/share/xfqtrace/versions/<version>/xfqtrace-kit` |
| macOS | `~/Library/Application Support/xfqtrace/versions/<version>/xfqtrace-kit` |
| Windows | `%LOCALAPPDATA%\xfqtrace\versions\<version>\xfqtrace-kit` |

`xfq doctor` 只检查环境。没有 KPM/`xfvmahide.kpm` 时要提醒，但普通 trace 不一定需要；如果要安装隐藏模块，按 doctor 给出的命令走 APatch/KernelPatch 授权/密码流程。

`libxfqtrace.so` 和 `xfinjectd` 都是 kit 必需文件。因为默认后端是 `xfinject`，所以 `xfq init`/`xfq doctor` 如果报缺 `bin/xfinjectd`，不要继续跑默认 trace，应该让用户重新安装完整 kit；`xj3`/frida-server 仍然不随 kit 打包，只在用户显式选择 `--inject-backend frida-server` 时才需要。

2.1+ kit 的样本可以只带 `examples/<package>/recipe.json`；`xfq init`/`xfq run` 必须兼容这种 recipe-only 样本，同时继续兼容 2.0 的 `半自动化trace.js` 样本。

## 2. AI 跑 trace 的命令

进入 kit 根目录，或使用绝对路径调用：

```bash
cd <kit-root>
python ./全自动化trace.py -p <package> --serial <serial> --inject-backend xfinject
```

常用命令：

```bash
# xfinject：推荐 AI 自动跑，显式指定后端
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend xfinject

# 本轮先清旧 trace/logcat，再跑；不会 pm clear app data
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend xfinject --clear-logs target

# 首启/隐私协议场景才清 app data
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend xfinject --clear-app-data

# 不要自动点击 UI
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend xfinject --no-auto-click

# 临时只验证 arm 链路；超时返回不代表 trace 成功/失败
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend xfinject --xfinject-timeout 60 --keep-running-on-timeout

# frida-server 后端；只有这个后端才有 bypass 意义
python ./全自动化trace.py -p com.target.app --serial <serial> --inject-backend frida-server --bypass bangbang
```

重要事实：

- Python 脚本源码默认 `--inject-backend frida-server`，所以 AI 想用 xfinject 必须显式传 `--inject-backend xfinject`。
- 普通启动前脚本会先 `am force-stop <package>`。
- 默认 auto-click 开启；默认不 `pm clear`，保留登录态/风控缓存。
- 默认 `--log-viewer none`：不把 xfQTrace logcat 实时刷到 Python 控制台。
- xfinject 后端会用通用 `-app-file` 把配置放到目标 App 的 `files/xfqtrace_config.json`，再通过 `xfqtrace_configure_file_and_start_async` 自启动；不要再按旧 `cache/xfqtrace_config.json` 排查。
- 脚本会在设备侧录 `xfQTrace` 日志，结束/失败后拉回本地。

## 3. 产物和日志怎么看

本地输出目录一般在：

```text
<kit-root>/examples/<package>/logs/<N>/
```

重点文件：

| 文件 | 用途 |
| --- | --- |
| `logcat.txt` | 最重要，包含 `xfQTrace`、崩溃、JNI 错误等诊断信息。 |
| `crash_summary.txt` | 有崩溃时生成的摘要。 |
| `*.log.lz4` / `*.log` | trace 数据；有 lz4 时脚本会尝试自动解压。 |
| `*.meta` | 线程/block 元信息。 |

默认终端不显示实时 logcat；如果需要现场看：

```bash
python ./全自动化trace.py -p <package> --serial <serial> --inject-backend xfinject --log-viewer auto
# 或手动看设备日志
adb -s <serial> logcat -v threadtime -s xfQTrace
```

判断 trace 状态看关键字，不要靠固定 timeout：

| 关键字 | 含义 |
| --- | --- |
| `xfqtrace armed:` / `trace armed successfully` | hook 已挂上，不等于 trace 完成。 |
| `waiting for <lib> to load` | 目标 SO 还没出现。 |
| `found <lib> @ 0x...` | 目标 SO 找到。 |
| `trace begin` | 目标函数已触发，trace 开始。 |
| `flush #N: raw=... compressed=...` | 后台持续落盘；长 trace 中这是正常进度。 |
| `trace end` / `trace completed successfully` | trace 正常结束。 |
| `JNI DETECTED ERROR` | 多半是 `hook_format` 和真实 JNI 签名不一致。 |
| `Fatal signal` / `FATAL EXCEPTION` | App/注入/trace 过程崩溃。 |
| `skip: filter mismatch` | filter 没命中。 |
| `skip: another trace is already in progress` | 重入/多线程触发，但当前已有 trace 在跑。 |

## 4. 配置加载优先级

`全自动化trace.py` 按顺序加载：

1. `--script <path>`：完全使用指定 JS。
2. `--recipe <path-or-name>`：指定 recipe；支持绝对/相对路径，也支持包目录下的单个 JSON 文件。
3. `examples/<package>/recipe.json`：推荐，新样本优先写它。
4. `examples/<package>/半自动化trace.js`：旧 CONFIG 脚本。
5. kit 根目录 `半自动化trace.js`：兜底。

## 5. recipe.json 写法

`recipe.json` 必须是 JSON 对象，至少包含 `target` 和 `options`。JSON 里 `offset` 统一写十六进制字符串，例如 `"0x1234"`；不要写十进制，也不要写运行时绝对地址。

```json
{
  "package": "com.target.app",
  "app_version": "1.2.3",
  "target": {
    "type": "func",
    "so_name": "libtarget.so",
    "offset": "0x1234"
  },
  "options": {
    "inline_hook_backend": 2,
    "out_format": "traceui",
    "lz4_compression": { "enable": true, "level": 0 },
    "stop_condition": { "max_traces": 1 },
    "hook_format": { "args": "env,obj,jstr", "ret": "jstr" }
  },
  "notes": "可选：触发步骤、已知问题"
}
```

`app_version` 是备注字段，native 引擎不读取；它只表示这个 offset 是在哪个 App/APK 版本上确认的。未知就写 `"unknown"`，后面补。

JSON 本身不支持注释，所以版本号直接写在 `app_version`；安装包来源、触发步骤、历史偏移等补充信息写到 `notes`，不要为了备注版本号改变目录结构。

2.1+ kit 样本目录只保留一个 `examples/<package>/recipe.json`。如果要临时测试别的版本/偏移，单独放一个 JSON 并用 `--recipe <path>` 指定；不要在样本目录里维护 `recipes/` 子目录。

常用 `options`：

| 字段 | 说明 |
| --- | --- |
| `inline_hook_backend` | `0`=shadowhook，`1`=frida-gum，`2`=Dobby；一般先用 2。 |
| `out_format` | 常用 `traceui`；`xfqtrace` 信息更多但更大。 |
| `lz4_compression` | 建议 `{ "enable": true, "level": 0 }`。 |
| `stop_condition.max_traces` | 命中几次目标调用后自然停。 |
| `hook_format` | 参数/返回值类型，JNI 参数必须谨慎。 |
| `filter` / `filter_display` | 只 trace 指定调用。 |
| `anon_trace` | 目标进入匿名可执行段时继续跟踪。 |
| `memory_trace` | 内存访问记录，默认别开。 |
| `sync_flush` | 排查最后日志时临时开，性能很差。 |
| `logging` | native 日志节奏；不要把 pidcat/logcat 配到这里。 |
| `multi_thread_trace` | 多线程命中同一目标时分别创建 VM/logger；默认关，确认需要抓并发时再开。 |
| `trace_modules` | 默认排除的第三方库显式纳入，例如 `["libmmkv2.so"]`。 |
| `exclude_modules` | 额外模块排除，适合确认只是噪音的 App SO。 |
| `exclude` / `exclude_ranges` | 排除模块或地址段，减少公共库噪音。 |

## 6. hook_format 速查

JNI 参数通常：`x0=JNIEnv*`，`x1=this/jclass`，业务参数从 `x2` 开始。

```json
{ "args": "env,obj,jstr,jstr", "ret": "jstr" }
{ "args": "env,jclass,jobj,jstr,int", "ret": "jstr" }
{ "args": "env,_,jobj,jstr,jstr,jstr,jstr,jstr,jstr,jstr,jlong,jstr,jlist", "ret": "jobj" }
```

常用类型：`_`、`env`、`obj`/`jobj`、`jclass`、`jstr`、`jbarr`、`jarr`/`jobjarr`、`jlist`、`jset`、`jmap`、`int`、`long`/`jlong`、`bool`、`ptr`、`hex`、`cstr`、`buf.N`、`jmap.diff`/`jlist.diff`/`jbarr.diff`。

写错 `hook_format` 可能触发 CheckJNI/JNI abort；不确定时先不写或只写确认的参数。

## 7. filter / exclude 示例

```json
"filter": { "arg": 2, "type": "int", "op": "eq", "value": 10401 },
"filter_display": "env,obj,int,jobjarr"
```

```json
"filter": {
  "all": [
    { "arg": 2, "type": "int", "op": "eq", "value": 10401 },
    { "arg": 4, "type": "jstr", "op": "contains", "value": "mini/rp" }
  ]
}
```

```json
"filter": {
  "arg": 2,
  "type": "jbarr",
  "op": "contains",
  "encoding": "hex",
  "value": "504B0304"
}
```

```json
"exclude": { "modules": ["libc.so", "libart.so", "liblog.so"] }
```

默认模块策略是 anchor SO 一定纳入、App SO/匿名段 on-demand 纳入、系统/运行时/trace 工具自身硬排除，常见第三方基础库如 `libmmkv*`、`libprotobuf*`、`libfbjni*`、`libcurl*`、`libcrypto.so`、`libssl.so`、`libc++_shared.so` 默认不 on-demand 纳入。需要覆盖时用：

```json
"trace_modules": ["libmmkv2.so"],
"exclude_modules": ["libnoise.so"]
```

优先级是：硬排除和 `exclude_modules` > `trace_modules` > 默认第三方排除 > on-demand 分类。

`multi_thread_trace=true` 会让多个线程命中同一目标时各自创建独立 QBDI VM 和 `_t<tid>` trace 文件；它不排队、不改变 App 调度，但文件会更多更大。

```json
"exclude_ranges": [
  { "start": "0x7000000000", "end": "0x7000010000", "reason": "known dispatcher" }
]
```

新样本不要一开始乱排除；先跑通最小配置，再按 trace 噪音和体积加。

## 8. Shopee 被动监听 + 主动调用模式

Shopee 示例里有一类很适合回归的写法：先被动等目标 SO 加载并 arm trace，再主动调用 Java/JNI 入口，用 marker + filter 只捕获关心的那次 trace。遇到用户问“怎么稳定触发 Shopee / 怎么只抓自己构造的请求”时，优先看：

```text
examples/com.shopee.vn/recipe.json
examples/com.shopee.vn/主动调用验证.js
```

要点：

- `android_dlopen_ext` 监听目标 `libshpssdk.so`，SO 一出现就 arm。
- arm 成功后 `setTimeout(triggerTestCall, delay_ms)` 主动调用 `com.shopee.shpssdk.wvvvuwwu.vuwuuwvw(byte[], byte[])`。
- payload 里写入 `TRACE_MARKER = "xfqtrace_manual_" + Date.now().toString(16)`。
- `filter_expr` 按 marker 过滤，例如：`x3:jbarr contains hex('<marker>')`，避免把自然业务调用也抓进来。
- 如果只验证 Java/JNI 主动调用是否可用，先跑 `主动调用验证.js`；它不加载 trace 引擎，只打印真实返回值。

这个模式的价值是把“等待业务自然触发”变成“trace armed 后主动触发”，适合 smoke、回归和定位 `hook_format/filter`。

注意：当前默认 kit 是 lite 包，不内置 Shopee APK。使用这个 smoke 前先确认设备已安装 `com.shopee.vn`；如果用户拿的是 full 包或自己把 APK 放进示例目录，`xfq run` 才可能自动安装。

## 9. 注入后端选择

| 维度 | xfinject | frida-server |
| --- | --- | --- |
| 设备侧 server | 不需要 | 需要用户自备/启动。 |
| Frida JS/bypass | 不执行 JS bypass | 支持 `--bypass`。 |
| 默认建议 | AI 自动 trace 优先用 | 旧样本或必须 bypass 时用。 |
| 检测判断 | 不按 Frida 检测解释 | 可能被 Frida 检测。 |

frida-server 不打包进 kit。项目推荐环境：设备侧 `/data/local/tmp/xj3`，Python `frida==16.2.1`、`frida-tools==12.0.0`，设备 server 推荐 16.5.7。

启动示例：

```bash
adb -s <serial> shell su -c '/data/local/tmp/xj3 >/dev/null 2>&1 &'
adb -s <serial> shell pidof xj3
```

## 10. 失败诊断按这四类分

### App 自身问题

先验证不注入时 app 能不能打开：

```bash
adb -s <serial> shell monkey -p <package> 1
```

常见证据：`Unable to instantiate appComponentFactory`、`ClassNotFoundException`、裸启动闪退、什么都不做也打不开。还有：offset 错、业务没触发、filter 太严、SO 在另一个进程、`hook_format` 导致 CheckJNI、`Fatal signal`。

### 环境不干净

测 xfinject 前建议：

```bash
adb -s <serial> shell su -c 'pkill -f xj3; pkill -f frida-server; true'
adb -s <serial> shell am force-stop <package>
```

排查旧进程、旧 `/data/data/<package>/files/xfqtrace_config.json`、选错 serial、frida-server 残留。

### Frida 检测没过

只在 `--inject-backend frida-server` 时考虑。xfinject 下 `--bypass` 会被忽略；如果 xfinject 也崩，优先看 App 自身问题、环境或 trace 引擎问题。

### 工具行为/配置问题

- `armed` 但无 `trace begin`：业务没触发、地址错、filter 太严或进程不对。
- 长时间 `flush #...`：可能是 trace 很久，不要用 timeout 断言失败。
- `skip: another trace is already in progress`：重入/并发触发，不是 Python 卡死。
- `shadowhook init failed`：优先用 `inline_hook_backend: 2`。

## 11. xfq clean 到底清什么

```bash
xfq clean --traces
```

只清本机当前已安装 kit 下：

```text
<kit-root>/examples/*/xfqtrace_logs
```

不会清设备 `/sdcard`、不会清 `/data/data/<package>`、不会 `pm clear`。

```bash
xfq clean --all-versions   # 删除旧 kit 版本，保留当前版本
xfq clean --version <v>    # 删除指定版本
```

## 12. 反馈给用户/作者时要带这些

```text
package: <包名和版本>
backend: xfinject | frida-server
command: <完整命令>
target: libxxx.so!0x偏移
recipe/js: <recipe.json 或 CONFIG 关键片段>
steps: <触发步骤，是否登录/清缓存/首启>
logs: <logcat.txt 关键段或路径>
trace_dir: <本地输出目录>
```

不要只说“没触发/崩溃”。必须能区分：SO 没加载、已 arm 但业务没走、地址错、hook_format 错、检测崩溃、还是 trace 正在正常跑。
