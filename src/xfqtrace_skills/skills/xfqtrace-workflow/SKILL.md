---
name: xfqtrace-workflow
description: 当智能体需要帮助用户安装 xfQTrace kit、配置 trace 目标、解释 JSON/hook_format/filter、分析 trace 产物/logcat/崩溃、处理 xfinject/frida-server 后端选择或排查 trace 不触发/不完成问题时使用。主路径：xfq init → xfq doctor → python 全自动化trace.py。公开 pip 包不包含 kit/APK/密码，kit 需要进知识星球获取。
---

# xfQTrace 智能体工作流

> 这个技能只给智能体用。给用户的回答保持简短、偏操作。不要虚构成功 trace。

## 设计思想

```
xfq                         ← 辅助工具：装 kit、检查环境、清理、看路径
  ├─ xfq init              ← 安装 kit（解压 zip 到 ~/.local/share/xfqtrace/）
  ├─ xfq doctor            ← 检查 adb/kit/设备/frida-server/kpm
  ├─ xfq clean             ← 清理本地 trace 产物
  ├─ xfq paths             ← 查看安装路径
  └─ xfq update            ← 更新 xfq CLI 自身

python 全自动化trace.py     ← AI 用它跑 trace，xfq run 只是它的封装
  └─ 所有参数直接传，AI 需要精确控制
```

**核心**：xfq 不跑 trace，跑 trace 用 Python 脚本。xfq run 是给人用的简化封装，AI 应该直接调 Python 脚本。

## 一、环境准备（用 xfq）

用户第一次用时，让用户：

```bash
# 下载 kit zip（进 x1a0f3n9 知识星球获取）
xfq init ./xfqtrace-kit-<version>.zip -p <password>
# Windows 可用 --dir 指定位置: xfq init .qtrace-kit-<version>.zip -p <password> --dir D:\xfqtrace
xfq doctor --serial <device-serial>
```

### Kit 装在哪

`xfq init` 安装后，AI 需要知道 `全自动化trace.py` 的路径：

```bash
# 让用户运行这个命令查看确切路径
xfq paths
```

默认位置：

| 系统 | Kit 根目录 |
|---|---|
| Linux/macOS | `~/.local/share/xfqtrace/versions/<version>/` |
| Windows | `%LOCALAPPDATA%/xfqtrace/versions/<version>/` |
| 自定义 | `xfq init .qtrace-kit-<version>.zip -p <password> --dir D:\xfqtrace

Kit 根目录下的 `全自动化trace.py` 就是 AI 跑 trace 用的入口脚本。

### 安装后的目录结构


```
<kit-root>/
├── 全自动化trace.py           # AI 跑 trace 用的 Python 入口
├── 半自动化trace.js            # 默认 JS 兜底脚本（xfinject 读它的 CONFIG）
├── manifest.json
├── bin/
│   ├── libxfqtrace.so          # Android 侧 trace payload
│   ├── lz4 / lz4.exe           # 解压用
│   ├── pidcat / pidcat.exe     # 彩色 logcat
│   └── xfvmahide.kpm           # KernelPatch 隐藏模块（可选）
├── helpers/                    # bypass / auto-click / xfinject_backend
└── examples/
    ├── com.shopee.vn/          # 烟雾测试样本
    └── <package>/              # 其他样本
```

## 二、跑 trace（AI 用 Python 脚本）

**不要用 `xfq run`**。AI 直接调 Python 脚本：

```bash
python <kit-root>/全自动化trace.py -p <package> --serial <serial> --inject-backend xfinject
```

### 典型命令

```bash
# 默认 xfinject + 自动点击
python 全自动化trace.py -p com.shopee.vn --serial 13081FDD4002VL

# 指定后端
python 全自动化trace.py -p com.shopee.vn --serial XXX --inject-backend frida-server

# 不清数据（保留登录态）
python 全自动化trace.py -p com.shopee.vn --serial XXX --no-clear-app-data

# 关自动点击
python 全自动化trace.py -p com.shopee.vn --serial XXX --no-auto-click

# 清缓存 + 跑
python 全自动化trace.py -p com.shopee.vn --serial XXX --clear-app-data

# 只用 frida-server + bypass
python 全自动化trace.py -p com.starbucks.cn --serial XXX --inject-backend frida-server --bypass bangbang
```

### 重要行为

- **每次默认先 `force-stop`** 旧进程
- **默认 auto-click 开启**：自动点隐私协议/权限弹窗
- **默认 clear-app-data 关闭**：保留登录态
- **默认 log-viewer 不开启**：logcat 录到设备 `/sdcard/`，trace 完后拉回
  - 如需终端实时看：加 `--log-viewer auto`
- **日志文件等级**：`--console-log-level I`（终端），`--log-file-level V`（文件）

### 输出目录

```
<kit-root>/examples/<package>/xfqtrace_logs/<N>/
├── logcat.txt              # 最重要的诊断文件
├── crash_summary.txt       # 崩溃摘要（有崩溃才生成）
├── *.log.lz4 / *.log       # trace 数据（自动 lz4 解压）
└── *.meta                  # 线程/block 元信息
```

### 完整参数列表

| 参数 | 说明 | 默认值 |
|---|---|---|
| `-p / --package` | **必填** 目标包名 | 无 |
| `--serial` | ADB 设备序列号 | 自动找 |
| `--inject-backend` | 注入后端：`xfinject` / `frida-server` | `frida-server`（Python 脚本默认） |
| `--attach` | 附加运行中进程，不 spawn | false |
| `--script` | 自定义 JS 脚本路径 | 自动找 |
| `--xfinject-timeout` | 等待秒数（0=无限） | 0 |
| `--keep-running-on-timeout` | 超时后保留现场 | false |
| `--vma-hide` | VMA 隐藏模式 | `auto` |
| `--reinstall` | 卸载重装 APK | 无 |
| `--pull-only` | 只拉已有产物 | false |
| `--no-push` | 跳过 push SO（SO 已在设备） | false |
| `--no-decompress` | 不自动解压 lz4 | false |
| `--clear-app-data` | `pm clear` 清数据 | false |
| `--no-clear-app-data` | 强制不清数据 | false |
| `--auto-click` | UI 自动点击（隐私弹窗） | true |
| `--no-auto-click` | 关自动点击 | false |
| `--clear-logs` | 清日志：`target` / `all` | 不清 |
| `--clear-only` | 只清日志退出 | false |
| `--log-viewer` | 终端日志：`none`/`auto`/`pidcat`/`logcat` | `none` |
| `--console-log-level` | 终端日志等级 | `I` |
| `--log-file-level` | 文件日志等级 | `V` |
| `--bypass` | 预注入反检测（仅 frida-server） | 无 |

> 注意：Python 脚本 `--inject-backend` 默认是 `frida-server`。AI 显式传 `--inject-backend xfinject` 切换。

## 三、注入后端选择

| 维度 | xfinject | frida-server |
|---|---|---|
| 设备侧 server | 不需要 | 需自带server|
| JS 注入 | 不支持 | 支持 bypass |
| 时机 | SO 加载后 arm（dlopen hook） | spawn 模式 |
| 检测绕过 | 无 frida 特征 | 需 bypass |
| 适用 | 新样本、无 JS 依赖 | 旧样本、需 bypass |

启动 frida-server：

```bash
adb -s <serial> shell su -c '/data/local/tmp/xj3 >/dev/null 2>&1 &'
adb -s <serial> shell pidof xj3
```

## 四、配置（recipe.json / CONFIG）

Python 脚本加载优先级：
1. `--script <path>` → 指定 JS 文件
2. `examples/<package>/recipe.json` → 纯 JSON 格式
3. `examples/<package>/半自动化trace.js` → JS 格式（含 `const CONFIG = {...}`）
4. 根目录 `半自动化trace.js` → 兜底

### recipe.json（推荐）

```json
{
  "package": "com.target.app",
  "target": {
    "type": "func",
    "so_name": "libtarget.so",
    "offset": 74565
  },
  "options": {
    "inline_hook_backend": 2,
    "out_format": "traceui",
    "lz4_compression": { "enable": true, "level": 0 },
    "stop_condition": { "max_traces": 1 },
    "hook_format": { "args": "env,_,jobj,jstr,jlong", "ret": "jstr" }
  }
}
```

`offset` 写十进制，交流时用 `libtarget.so!0x12345`。

### CONFIG（JS 文件格式，xfinject 也能读）

```javascript
const CONFIG = {
    package: "com.target.app",
    target: {
        type: "func",
        so_name: "libtarget.so",
        offset: 0x1234,
    },
    options: {
        inline_hook_backend: 2,
        out_format: "traceui",
        lz4_compression: { enable: true, level: 0 },
        stop_condition: { max_traces: 1 },
        hook_format: { args: "env,_,jobj,jstr", ret: "jstr" },
    },
};
```

### options 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `inline_hook_backend` | int | `0`=shadowhook, `1`=frida-gum, `2`=Dobby（推荐） |
| `out_format` | string | `"traceui"` 常规, `"xfqtrace"` 内部格式 |
| `lz4_compression` | object | `{"enable":true,"level":0}` |
| `stop_condition` | object | `{"max_traces":1}` 触发 N 次后停 |
| `hook_format` | object | 参数/返回值类型，JNI 必写 |
| `filter` | object | 采集条件 |
| `filter_display` | string | 命中时显示格式 |
| `exclude_ranges` | array | 排除 SO 内部分 offset 不插桩 |
| `memory_trace` | bool | 内存读写，默认 false |
| `logging` | object | 日志等级控制 |

### hook_format

```json
{ "args": "env,_,jobj,jstr,jlong", "ret": "jstr" }
```

常用类型：`env` / `_` / `jobj` / `jcls` / `jstr` / `jlist` / `jbarr` / `jarr` / `jint` / `jlong` / `ptr` / `cstr` / `void`

**写错 → CheckJNI 崩溃。不确定就不写。**

JNI 例子：

```json
// nativeSign(Context, String, long) → String
{ "args": "env,_,jobj,jstr,jlong", "ret": "jstr" }

// SMSDK.w1(Context, String..., List) → Object
{ "args": "env,_,jobj,jstr,jstr,jstr,jstr,jstr,jstr,jstr,jlong,jstr,jlist", "ret": "jobj" }

// doCalc(int, byte[], int) → int
{ "args": "env,_,jint,jbarr,jint", "ret": "jint" }
```

### filter

```json
// 整数过滤
{ "arg": 2, "type": "int", "op": "eq", "value": 10401 }
// 字符串包含
{ "arg": 3, "type": "jstr", "op": "contains", "value": "api" }
// byte[] 前缀
{ "arg": 4, "type": "jbarr", "op": "prefix", "encoding": "hex", "value": "01020304" }
// 组合
{ "all": [{ "arg": 2, "type": "int", "op": "eq", "value": 10401 }, { "arg": 3, "type": "jstr", "op": "contains", "value": "api" }] }
```

### exclude_ranges

```json
"exclude_ranges": [
  { "start": "0x12000", "end": "0x12800" }
]
```

相对 SO 基址偏移，半开 `[start, end)`。不要排除目标函数入口。

## 五、常见失败诊断

### 1️⃣ App自身的问题

**Trace 跑完了但没拿到想要的调用**
- offset 不对 — 最常犯，确认真函数地址是不是对的
- 业务没触发 — 需要点按钮、清缓存、登录才能走到目标函数
- filter 太严 — 搜 logcat 里 `skip: filter mismatch`，看是不是过滤掉了
- SO 在多进程（`:pushservice` 等）— 确认目标 SO 加载在哪个进程

**App 直接崩溃**

**App 打不开 / 闪退 / 没反应**
- 先确认 app 本身能不能正常打开 — 不用工具，直接 `adb shell monkey -p <pkg> 1` 启动
- `Unable to instantiate appComponentFactory` — APK 自身问题，跟注入无关
- 装了兼容性问题（targetSdkVersion 不匹配等）— 检查 logcat 里其他错误标签
- 有时就是 APK 版本/设备不兼容，换版本或换设备试
- `JNI DETECTED ERROR` — hook_format 写错了（`jobj` 写成 `jint`），检查参数个数和类型
- `Fatal signal` — 注入时机太晚或反调试冲突
- `Unable to instantiate appComponentFactory` — APK 自身问题，不关工具的事
- 可以先换 `inline_hook_backend: 0`(shadowhook) / `1`(frida-gum) / `2`(dobby) 试

**SO 一直不出现**
- so_name 写错了，`adb shell grep libxxx /proc/<pid>/maps` 看看
- 多进程 app，SO 可能还没加载或加载在子进程
- 已 hook `__loader_dlopen` / `__loader_android_dlopen_ext`，理论上 SO 一出现就能抓到

### 2️⃣ 环境不干净

**Trace 结果异常、进程启动不对**
- 之前跑过 frida-server 没杀掉就切 xfinject 了 — 先 `adb shell su -c "pkill xj3"` 杀掉，重启 app 再试
- 旧进程还在 — xfinject 默认 spawn 但可能错过子进程，先 `adb shell am force-stop <pkg>`
- 设备上残留旧的 xfqtrace_config.json — `xfq run` 会 force-stop，也清理 `/data/data/<pkg>/cache/`，手动跑时注意

**ADB 问题**
- `adb devices` 看看设备在不在，序列号对不对
- 多设备时没传 `--serial`

### 3️⃣ Frida 检测没过

**用了 frida-server 后端**
- frida-server 特征太明显，app 检测到了就闪退/不触发
- 需要加 `--bypass bangbang` 或 `--bypass apiguard3`
- bypass 脚本在 `helpers/bypass_*.js`，目前支持：msa、bangbang、apiguard3、dump_apiguard3

**用了 xfinject 后端**
- xfinject 没有 frida 特征，不存在检测问题
- `--bypass` 参数在 xfinject 下会被忽略
- 如果还是崩溃，属于 app 自身问题或环境问题，不是 frida 检测

### 4️⃣ 工具行为类

**Trace 不结束 / 很久**
- 10-30 分钟正常 — 不是卡死，看 logcat 里 `flush #N: raw=... compressed=...` 是否在持续涨
- `stop_condition` 没设 `max_traces` 或值太大，trace 不会自己停，靠业务触发
- **不要用超时判失败**，看 flush 量和 logcat 里 `trace end` / `trace completed successfully`

**完全没有任何日志输出**
- `DEFAULT_LOG_VIEWER = "none"`，默认不开终端 logcat
- 设备侧日志录到 `/sdcard/`，trace 完后 `adb pull` 拉回
- 如需终端实时看：加 `--log-viewer auto`
- `stop_condition` 没设 `max_traces` 或值很大

## 六、logcat 关键字速查

在 `logcat.txt` 里搜：

| 关键字 | 含义 |
|---|---|
| `==========================================================================` | banner，libxfqtrace.so 已加载 |
| `xfqtrace armed:` / `trace armed successfully` | hook 已挂上（不等同 trace 完成） |
| `waiting for <lib> to load` | SO 还没出现 |
| `found <lib> @ 0x...` | SO 找到 |
| `trace begin` | trace 开始 |
| `trace end` / `trace completed successfully` | trace 正常完成 |
| `flush #N: raw=... compressed=...` | 写盘心跳（数据在涨就是好的） |
| `config error` / `start error` | 配置失败 |
| `skip: filter mismatch` | filter 没命中（正常） |
| `skip: another trace is already in progress` | 正在 trace，忽略重复 |
| `Fatal signal` / `FATAL EXCEPTION` | 应用崩溃 |
| `JNI DETECTED ERROR` | hook_format 写错 |

## 七、样本反馈格式
给项目作者的反馈指南
```text
apk: <包名 / 版本 / 来源>
json: <recipe.json 或 CONFIG>
target: libxxx.so!0x<offset>
sig: <JNI 函数名和签名>
steps: <触发步骤 + 清缓存/登录>
backend: xfinject | frida-server
logs: <logcat.txt 路径>
```

## 八、实时看日志 / 更新 / 提醒

### 实时看日志（手动用 adb）

```bash
adb -s <serial> logcat -v threadtime -s xfQTrace
adb -s <serial> logcat -v threadtime | grep -E 'xfQTrace|FATAL|crash|JNI'
```

### 更新

- **xfq CLI**：`xfq update` 或自动检测按 y
- **Kit / libxfqtrace.so**：进知识星球下载新版 → `xfq init <new.zip> -p <password> --force`
- **AI 技能**：pip 更新后自动刷新；也可 `xfq skill install --target both --force`

### 提醒

- `xfq doctor` 只检查不清理，清理用 `xfq clean`。
- `xfq clean --traces`：清理本机 examples/*/xfqtrace_logs，不清设备侧文件。
- `xfq clean --all-versions`：删除所有旧 kit 版本（保留当前版本）。
- `xfq clean --version <v>`：删除指定版本。
- `trace armed successfully` ≠ trace 完成。要看 `trace end` / `completed`。
- 长 trace 不能靠超时判失败。看 flush 量。
- offset 交流用 `libxxx.so!0x1234`，JSON 写十进制。
- **默认不开终端 logcat**，设备侧录文件，trace 完后拉回。要实时看加 `--log-viewer auto`。
- **不要通过改代码把失败 trace 伪装成成功。**
- 默认会 force-stop。要保留登录态别加 `--clear-app-data`。
