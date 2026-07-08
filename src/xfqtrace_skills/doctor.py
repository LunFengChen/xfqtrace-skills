from __future__ import annotations

import importlib.metadata
import json
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
import os
from typing import Any

from . import __version__
from .bundle import Bundle, XfqError, bundle_tool_status, default_sample_entry, load_active_bundle, list_versions, validate_bundle_root
from .skill_install import skill_status
from .update_check import fetch_channel, newer



def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return 999, "", str(exc)


def _tool_version(path: str | None, kind: str) -> str | None:
    if not path:
        return None
    if kind == "adb":
        rc, out, err = _run([path, "version"], timeout=3)
        text = "\n".join(x for x in [out, err] if x)
        m = re.search(r"\bversion\s+([0-9][0-9A-Za-z.+_-]*)", text, re.I)
        return m.group(1) if rc == 0 and m else None
    if kind == "lz4":
        rc, out, err = _run([path, "--version"], timeout=3)
        text = "\n".join(x for x in [out, err] if x)
        m = re.search(r"\bv?([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)\b", text)
        return m.group(1) if rc == 0 and m else None
    if kind == "pidcat":
        rc, out, err = _run([path, "--version"], timeout=3)
        text = "\n".join(x for x in [out, err] if x)
        m = re.search(r"\bpidcat\s+([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)\b", text, re.I)
        return m.group(1) if rc == 0 and m else None
    if kind == "7z":
        rc, out, err = _run([path], timeout=3)
        text = "\n".join(x for x in [out, err] if x)
        m = re.search(r"\b7-Zip\b.*?\b([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)\b", text)
        # 7z prints usage and exits 0 on Linux p7zip; tolerate non-zero variants.
        return m.group(1) if m else None
    return None


def _adb(serial: str | None, *args: str, timeout: int = 8) -> tuple[int, str, str]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return _run(cmd, timeout=timeout)


def _adb_push(serial: str | None, local: Path, remote: str, timeout: int = 30) -> tuple[int, str, str]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["push", str(local), remote]
    return _run(cmd, timeout=timeout)


def _su(serial: str | None, line: str, timeout: int = 8) -> tuple[int, str, str]:
    return _adb(serial, "shell", "su", "-c", line, timeout=timeout)


def _kp_cmd(superkey: str, subcmd: str) -> str:
    return f"truncate {shlex.quote(superkey)} module {subcmd}"


def kpm_status(
    bundle: Bundle | None,
    serial: str | None,
    *,
    install: bool = False,
    superkey: str | None = None,
) -> dict[str, Any]:
    """Check and optionally install/load xfvmahide KPM via APatch/KernelPatch."""
    kpm_path = bundle.xfvmahide_kpm if bundle else None
    result: dict[str, Any] = {
        "module": "xfvmahide",
        "local_kpm": str(kpm_path) if kpm_path else None,
        "local_kpm_exists": bool(kpm_path and kpm_path.exists()),
        "backend": "truncate/APatch",
        "installed": False,
        "checked": False,
        "can_install": bool(serial and superkey and kpm_path and kpm_path.exists()),
        "mutated": False,
    }
    if not serial:
        result["problem"] = "no --serial, cannot check device"
        return result
    if not superkey:
        result["problem"] = "no KPM superkey (--kpm-superkey or XFQ_KPM_SUPERKEY)"
        return result

    rc, out, err = _su(serial, _kp_cmd(superkey, "list"), timeout=8)
    result["checked"] = True
    result["list"] = {"returncode": rc, "stdout": out, "stderr": err}
    result["installed"] = rc == 0 and "xfvmahide" in (out or "")

    if result["installed"] or not install:
        return _run_kpm_test(result, serial, superkey)

    if not (kpm_path and kpm_path.exists()):
        result["problem"] = "kit/bin/xfvmahide.kpm not found"
        return result

    remote_dir = "/data/local/tmp/mkpms"
    remote_kpm = f"{remote_dir}/xfvmahide.kpm"
    rc_mkdir, out_mkdir, err_mkdir = _su(serial, f"mkdir -p {shlex.quote(remote_dir)}", timeout=8)
    rc_push, out_push, err_push = _adb_push(serial, kpm_path, remote_kpm, timeout=60)
    rc_chmod, out_chmod, err_chmod = _su(serial, f"chmod 644 {shlex.quote(remote_kpm)}", timeout=8)
    rc_load, out_load, err_load = _su(serial, _kp_cmd(superkey, f"load {shlex.quote(remote_kpm)}"), timeout=15)
    result["mutated"] = True
    result["install_steps"] = {
        "mkdir": {"returncode": rc_mkdir, "stdout": out_mkdir, "stderr": err_mkdir},
        "push": {"returncode": rc_push, "stdout": out_push, "stderr": err_push},
        "chmod": {"returncode": rc_chmod, "stdout": out_chmod, "stderr": err_chmod},
        "load": {"returncode": rc_load, "stdout": out_load, "stderr": err_load},
    }
    rc2, out2, err2 = _su(serial, _kp_cmd(superkey, "list"), timeout=8)
    result["post_list"] = {"returncode": rc2, "stdout": out2, "stderr": err2}
    result["installed"] = rc2 == 0 and "xfvmahide" in (out2 or "")
    return _run_kpm_test(result, serial, superkey)


def _run_kpm_test(result: dict[str, Any], serial: str, superkey: str) -> dict[str, Any]:
    """Internal: verify xfvmahide actually hides a range from a shell-owned helper."""
    result["test"] = {"skipped": False, "passed": False}
    if not result.get("installed"):
        result["test"]["skipped"] = True
        return result

    # Read a range from the adb shell process's own /proc/self/maps.
    # xfvmahide filters by reading UID, so when the same shell process (UID 2000)
    # reads its own maps again after we add a rule for UID 2000, the range should disappear.
    rc_line, out_line, err_line = _adb(serial, "shell", "head -n 1 /proc/self/maps 2>/dev/null", timeout=8)
    line = (out_line or "").splitlines()[0] if out_line else ""
    if rc_line != 0 or not line or "-" not in line.split(" ", 1)[0]:
        result["test"]["error"] = err_line or f"bad maps line: {line!r}"
        return result

    range_tok = line.split(" ", 1)[0]
    start_hex, end_hex = range_tok.split("-", 1)
    result["test"]["range"] = range_tok

    _su(serial, _kp_cmd(superkey, "ctl0 xfvmahide clear"), timeout=8)
    rc_add, _, err_add = _su(serial, _kp_cmd(superkey, f"ctl0 xfvmahide add 2000 0x{start_hex} 0x{end_hex}"), timeout=8)
    if rc_add != 0:
        result["test"]["error"] = err_add or "failed to add hide rule"
        return result

    # Read the SAME process's maps again, still as uid 2000.  xfvmahide should filter.
    rc_hide, out_hide, err_hide = _adb(serial, "shell", f"grep -Fc -- '{range_tok}' /proc/self/maps 2>/dev/null", timeout=8)
    _su(serial, _kp_cmd(superkey, "ctl0 xfvmahide clear"), timeout=8)
    rc_restore, out_restore, err_restore = _adb(serial, "shell", f"grep -Fc -- '{range_tok}' /proc/self/maps 2>/dev/null", timeout=8)

    try:
        hid = int((out_hide or "0").strip() or "0")
    except ValueError:
        hid = -1
    try:
        res = int((out_restore or "0").strip() or "0")
    except ValueError:
        res = -1

    result["test"]["hide"] = hid
    result["test"]["restore_after_clear"] = res
    # If restore stays 0, the verification path is inconclusive on this device
    # (for example, /proc visibility restrictions for the chosen helper).
    if rc_hide != 0 or rc_restore != 0:
        result["test"]["error"] = err_hide or err_restore or f"rc_hide={rc_hide} rc_restore={rc_restore}"
        return result
    if res == 0:
        result["test"]["skipped"] = True
        result["test"]["reason"] = "verification unavailable on this device"
        return result
    result["test"]["passed"] = (hid == 0 and res >= 1)
    if not result["test"]["passed"]:
        result["test"]["error"] = f"hide={hid} restore={res}"
    return result




def _ascii_strings(path: Path, *, min_len: int = 4, max_bytes: int = 64 * 1024 * 1024) -> list[str]:
    """Extract printable strings from a local artifact without executing it."""
    if not path.exists() or not path.is_file():
        return []
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if len(data) > max_bytes:
        # Build/version metadata is in normal rodata/buildinfo for our artifacts;
        # cap reads so doctor cannot become unexpectedly heavy on broken files.
        data = data[:max_bytes]
    return [m.group(0).decode("utf-8", "replace") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data)]


def _first_preferring(values: list[str], preferred: tuple[str, ...]) -> str | None:
    for needle in preferred:
        for value in values:
            if needle in value:
                return value
    return values[0] if values else None


def _detect_file_artifact(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    strings = _ascii_strings(path)
    version = None
    for item in strings:
        if item.startswith("version="):
            version = item.split("=", 1)[1]
            break
    if version:
        info["version"] = version
    return info


def _detect_libxfqtrace_version(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    strings = _ascii_strings(path)
    candidates: list[str] = []
    version_re = re.compile(r"^v\d+(?:\.\d+)+(?:[-+._A-Za-z0-9]*)?$")
    for item in strings:
        if len(item) <= 48 and version_re.match(item):
            candidates.append(item)
    version = _first_preferring(candidates, ("-g", "v2.", "v1."))
    banner = next((x for x in strings if "xfQTrace" in x and "build" in x), None)
    info.update({
        "version": version,
        "banner": banner,
    })
    return info


def _parse_go_buildinfo(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    strings = _ascii_strings(path)
    go_version = next((x for x in strings if re.fullmatch(r"go\d+\.\d+(?:\.\d+)?", x)), None)
    module_path = None
    module_version = None
    build: dict[str, str] = {}
    try:
        data = path.read_bytes()
    except OSError:
        data = b""
    for raw in re.findall(rb"(?:path|mod|build)\t[^\x00\r\n]+", data):
        item = raw.decode("utf-8", "replace")
        if item.startswith("path\t"):
            info["main_path"] = item.split("\t", 1)[1]
        elif item.startswith("mod\t"):
            parts = item.split("\t")
            if len(parts) >= 3:
                module_path, module_version = parts[1], parts[2]
        elif item.startswith("build\t"):
            payload = item.split("\t", 1)[1]
            if "=" in payload:
                key, value = payload.split("=", 1)
                build[key] = value
    if go_version:
        info["go_version"] = go_version
    if module_path:
        info["module"] = module_path
        info["module_version"] = module_version
    if build:
        info["build"] = build
        if rev := build.get("vcs.revision"):
            info["revision"] = rev
            info["short_revision"] = rev[:12]
        if t := build.get("vcs.time"):
            info["time"] = t
        if m := build.get("vcs.modified"):
            info["modified"] = m.lower() == "true"
        if goos := build.get("GOOS"):
            info["goos"] = goos
        if goarch := build.get("GOARCH"):
            info["goarch"] = goarch
    return info


def _apply_manifest_component(info: dict[str, Any], component: Any) -> dict[str, Any]:
    if not isinstance(component, dict):
        return info
    if version := component.get("version"):
        info.setdefault("version", str(version))
    commit = component.get("commit") or component.get("revision")
    if commit:
        commit = str(commit)
        info["revision"] = commit
        info["short_revision"] = commit[:12]
    if component.get("dirty"):
        info["modified"] = True
    return info


def bundle_artifact_versions(bundle: Bundle | None, *, resolve_remote: bool = False) -> dict[str, Any]:
    if bundle is None:
        return {}
    components = bundle.manifest.get("components") or {}
    xfqtrace = _apply_manifest_component(
        _detect_libxfqtrace_version(bundle.bin_dir / "libxfqtrace.so"),
        components.get("xfqtrace"),
    )
    xfinject = _apply_manifest_component(
        _parse_go_buildinfo(bundle.xfinjectd_path),
        components.get("xfinject"),
    )
    xfvmahide = _apply_manifest_component(
        _detect_file_artifact(bundle.xfvmahide_kpm),
        components.get("xfvmahide"),
    )
    return {
        "xfqtrace": xfqtrace,
        "xfinject": xfinject,
        "xfvmahide": xfvmahide,
    }


def _detect_local_bundle() -> Bundle | None:
    """Detect a kit from current working directory or its parents.

    This makes `xfq doctor` useful when the user is already inside an
    extracted xfqtrace-kit repo but has not run `xfq init` yet.
    """
    cwd = Path.cwd().resolve()
    for cand in [cwd, *cwd.parents]:
        manifest = cand / "manifest.json"
        if not manifest.exists():
            continue
        try:
            bundle = validate_bundle_root(cand)
            # tag source for UI/reporting
            bundle.manifest.setdefault("bundle_source", "local")
            return bundle
        except Exception:
            continue
    return None



def bundle_summary(bundle: Bundle | None, *, resolve_remote_versions: bool = False) -> dict[str, Any]:
    if bundle is None:
        return {
            "installed": False,
            "problem": "xfqtrace-kit not initialized; run xfq init <zip> -p <password>",
            "source": None,
        }
    tools = bundle_tool_status(bundle)
    missing_required = [name for name, item in tools.items() if item.get("required") and not item.get("exists")]
    missing_recommended = [name for name, item in tools.items() if not item.get("required") and not item.get("exists")]
    return {
        "installed": True,
        "root": str(bundle.root),
        "source": bundle.manifest.get("bundle_source", "active"),
        "bundle_version": bundle.version,
        "engine_version": bundle.manifest.get("engine_version"),
        "entry": str(bundle.entry),
        "libxfqtrace": str(bundle.bin_dir / "libxfqtrace.so"),
        "default_test": bundle.default_test,
        "bundled_tools": tools,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "artifact_versions": bundle_artifact_versions(bundle, resolve_remote=resolve_remote_versions),
        "checks": {
            "manifest": (bundle.root / "manifest.json").exists(),
            "entry": bundle.entry.exists(),
            "libxfqtrace": (bundle.bin_dir / "libxfqtrace.so").exists(),
            "xfinjectd": bundle.xfinjectd_path.exists(),
            "default_sample": default_sample_entry(bundle) is not None,
            "lz4": (bundle.bin_dir / "lz4").exists() or (bundle.bin_dir / "lz4.exe").exists(),
            "pidcat": (bundle.bin_dir / "pidcat").exists() or (bundle.bin_dir / "pidcat.exe").exists(),
            "7z": (bundle.bin_dir / "7z").exists() or (bundle.bin_dir / "7z.exe").exists(),
            "xfvmahide_kpm": (bundle.bin_dir / "xfvmahide.kpm").exists(),
        },
    }


def doctor(
    serial: str | None = None,
    check_updates: bool = True,
    *,
    install_kpm: bool = False,
    kpm_superkey: str | None = None,
) -> dict[str, Any]:
    try:
        bundle = load_active_bundle()
        bundle.manifest.setdefault("bundle_source", "active")
    except XfqError:
        bundle = _detect_local_bundle()

    adb_path = shutil.which("adb")
    lz4_path = shutil.which("lz4")
    pidcat_path = shutil.which("pidcat") or shutil.which("pidcat.exe")
    seven_zip_path = shutil.which("7z") or shutil.which("7z.exe")
    frida_py = _dist_version("frida")
    frida_tools = _dist_version("frida-tools")
    result: dict[str, Any] = {
        "xfq_cli_version": __version__,
        "bundle": bundle_summary(bundle, resolve_remote_versions=check_updates),
        "installed_versions": list_versions(),
        "tools": {
            "python_frida": frida_py,
            "frida_tools": frida_tools,
            "adb": adb_path,
            "adb_version": _tool_version(adb_path, "adb"),
            "lz4_path": lz4_path,
            "lz4_version": _tool_version(lz4_path, "lz4"),
            "pidcat_path": pidcat_path,
            "pidcat_version": _tool_version(pidcat_path, "pidcat"),
            "7z_path": seven_zip_path,
            "7z_version": _tool_version(seven_zip_path, "7z"),
        },
        "backend_notes": {
            "default_backend": "xfinject",
            "xfinject_requires_frida_server": False,
            "frida_server_required_only_when": "--inject-backend frida-server",
            "recommended_device_frida_server": "16.5.7（xiaojia 588 knowledge planet v3, not bundled）",
            "recommended_python_frida": "frida==16.2.1",
            "recommended_frida_tools": "frida-tools==12.0.0",
        },
        "skills": [asdict(s) for s in skill_status("both")],
    }

    if adb_path:
        rc, out, err = _adb(None, "devices")
        result["adb_devices"] = {"ok": rc == 0, "stdout": out, "stderr": err}
        if serial:
            rc, out, err = _adb(serial, "shell", "echo", "ok")
            online = rc == 0 and out.strip() == "ok"
            device_info: dict[str, Any] = {"serial": serial, "online": online, "error": err}
            if online:
                rc_props, props_out, props_err = _adb(
                    serial,
                    "shell",
                    "getprop ro.product.manufacturer; "
                    "getprop ro.product.model; "
                    "getprop ro.product.device; "
                    "getprop ro.build.version.release; "
                    "getprop ro.build.version.sdk; "
                    "getprop ro.product.cpu.abi",
                    timeout=8,
                )
                vals = [line.strip() for line in (props_out or "").splitlines()]
                if rc_props == 0 and len(vals) >= 6:
                    device_info.update({
                        "manufacturer": vals[0],
                        "model": vals[1],
                        "device": vals[2],
                        "android": vals[3],
                        "sdk": vals[4],
                        "abi": vals[5],
                    })
                elif props_err:
                    device_info["props_error"] = props_err
            result["device"] = device_info
            result["kpm"] = kpm_status(bundle, serial, install=install_kpm, superkey=kpm_superkey)

    if check_updates:
        channel = fetch_channel()
        active_version = bundle.version if bundle else None
        result["updates"] = {
            "channel": channel,
            "cli_update_available": newer(channel.get("cli_version"), __version__),
            "bundle_update_available": newer(channel.get("latest_bundle_version"), active_version),
            "hint": channel.get("download_hint"),
        }
    return result




def display_plain_version(version: Any) -> str:
    if version is None or version == "":
        return "unknown"
    text = str(version)
    if re.match(r"^v\d+(?:\.\d+)+(?:[-+._A-Za-z0-9]*)?$", text):
        return text[1:]
    return text

def print_human_doctor(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("═" * 54)
    lines.append(f"  xfqtrace-skills  version={display_plain_version(result.get('xfq_cli_version'))}")
    lines.append("─" * 54)

    def yn(ok: bool) -> str:
        return "OK" if ok else "MISSING"

    bundle = result.get("bundle", {})
    if bundle.get("installed"):
        lines.append("  xfqtrace-kit")
        artifacts = bundle.get("artifact_versions") or {}
        xfq = artifacts.get("xfqtrace") or {}
        xfi = artifacts.get("xfinject") or {}
        xfv = artifacts.get("xfvmahide") or {}
        checks = bundle.get("checks") or {}
        module_version = xfi.get("module_version")
        if module_version in {None, "", "(devel)"}:
            module_version = None
        xfi_version = xfi.get("release_tag") or module_version
        kpm = result.get("kpm")
        xfv_status_extra = None
        if kpm and kpm.get("checked"):
            if kpm.get("installed"):
                test = kpm.get("test") or {}
                if test.get("passed"):
                    xfv_status_extra = "kpm installed/test OK"
                elif test.get("skipped"):
                    xfv_status_extra = "kpm installed/test skipped"
                else:
                    xfv_status_extra = "kpm installed"
            else:
                xfv_status_extra = "kpm not installed"
        elif kpm and not kpm.get("checked") and kpm.get("problem"):
            problem = str(kpm.get("problem"))
            if "no KPM superkey" in problem:
                problem = "no superkey"
            xfv_status_extra = f"device not checked: {problem}"

        def display_version(version: str | None) -> str:
            return display_plain_version(version)

        def component_row(
            name: str,
            version: str | None,
            commit: str | None,
            *,
            exists: bool = True,
            dirty: bool = False,
            status_extra: str | None = None,
        ) -> str:
            if not exists:
                status = "missing"
            elif dirty:
                status = "dirty"
            else:
                status = "clean"
            if status_extra:
                status = f"{status}; {status_extra}"
            return (
                f"           {name:<10} "
                f"version={display_version(version)}  "
                f"commit={commit or 'unknown'}  "
                f"status={status}"
            )

        lines.append(component_row(
            "xfqtrace",
            xfq.get("version"),
            xfq.get("short_revision"),
            exists=bool(xfq.get("exists")),
            dirty=bool(xfq.get("modified")),
        ))
        lines.append(component_row(
            "xfinject",
            xfi_version,
            xfi.get("short_revision"),
            exists=bool(xfi.get("exists")),
            dirty=bool(xfi.get("modified")),
        ))
        lines.append(component_row(
            "xfvmahide",
            xfv.get("version"),
            xfv.get("short_revision"),
            exists=bool(checks.get("xfvmahide_kpm")),
            dirty=bool(xfv.get("modified")),
            status_extra=xfv_status_extra,
        ))
        if kpm and not kpm.get("checked") and kpm.get("local_kpm_exists"):
            lines.append("                     cmd: xfq doctor --serial <serial> --install-kpm --kpm-superkey <key>")
        mr = bundle.get("missing_required", [])
        if mr:
            lines.append(f"           [red]缺必要工具: {', '.join(mr)}[/red]")
        if bundle.get("missing_recommended"):
            lines.append(f"           缺可选: {', '.join(bundle['missing_recommended'])}")
        if bundle.get("source") == "local":
            lines.append("           (local repo, 未 xfq init)")
    else:
        lines.append(f"  xfqtrace-kit  [red]未安装[/red]")

    device = result.get("device")
    if device:
        lines.append("─" * 54)
    if device:
        serial = device.get("serial", "?")
        ok = device.get("online", False)
        lines.append(f"  device   {'OK' if ok else 'FAIL'}  serial={serial}")
        if ok:
            android = device.get("android") or "?"
            sdk = device.get("sdk") or "?"
            model = " ".join(x for x in [device.get("manufacturer"), device.get("model")] if x) or "?"
            codename = device.get("device") or "?"
            abi = device.get("abi") or "?"
            lines.append(f"           android={android} sdk={sdk}  model={model} ({codename})  abi={abi}")

    lines.append("─" * 54)
    tools = result.get("tools", {})
    def tool_row(name: str, path_key: str, version_key: str) -> str:
        exists = bool(tools.get(path_key))
        version = tools.get(version_key) or "unknown"
        return f"           {name:<6} version={version:<8} status={yn(exists)}"

    lines.append("  tools")
    lines.append(tool_row("adb", "adb", "adb_version"))
    lines.append(tool_row("lz4", "lz4_path", "lz4_version"))
    lines.append(tool_row("pidcat", "pidcat_path", "pidcat_version"))
    lines.append(tool_row("7z", "7z_path", "7z_version"))
    lines.append("─" * 54)
    lines.append("  frida")
    lines.append(f"           frida={tools.get('python_frida') or 'missing'}")
    lines.append(f"           frida-tools={tools.get('frida_tools') or 'missing'}")
    return "\n".join(lines)
