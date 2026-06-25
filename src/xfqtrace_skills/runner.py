from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import Bundle, XfqError, load_active_bundle

SMOKE_PACKAGE = "com.shopee.vn"
DEFAULT_SCRIPT = "半自动化trace.js"
DEFAULT_RUN_ARGS = ["--inject-backend", "xfinject", "--clear-logs", "target", "--no-decompress"]


@dataclass(frozen=True)
class TraceTarget:
    name: str
    package: str
    root: Path
    script: Path
    apk: Path | None
    default_args: list[str]


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _first_app_package(root: Path) -> Path | None:
    for pattern in ("*.apk", "*.xapk"):
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0]
    return None


def load_recipe(name: str, bundle: Bundle | None = None) -> TraceTarget:
    """Resolve a CLI target to the kit entry script inputs.

    Kept as load_recipe for old imports; there is no user-facing recipe file.
    """
    bundle = bundle or load_active_bundle()
    target = bundle.default_test if name == "test" else name
    if target in {"shp", "shopee"}:
        target = SMOKE_PACKAGE

    root = bundle.examples_dir / target
    if not root.exists() and target == SMOKE_PACKAGE:
        legacy = bundle.examples_dir / "shp"
        if legacy.exists():
            root = legacy

    package = SMOKE_PACKAGE if target == SMOKE_PACKAGE else target
    script = root / DEFAULT_SCRIPT
    if not script.exists() and target == SMOKE_PACKAGE:
        fallback = _first_existing([
            root / "半自动化trace_3.71.31.js",
            root / "半自动化trace_3.66.26.js",
        ])
        if fallback:
            script = fallback

    apk = _first_app_package(root)
    return TraceTarget(
        name=name,
        package=package,
        root=root,
        script=script,
        apk=apk,
        default_args=list(DEFAULT_RUN_ARGS),
    )


def _adb(serial: str | None, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def ensure_apk_installed(target: TraceTarget, serial: str | None) -> bool:
    if target.apk is None:
        return False
    if not target.apk.exists():
        raise XfqError(f"apk not found: {target.apk}")
    if target.apk.suffix.lower() != ".apk":
        raise XfqError(f"only .apk auto-install is supported currently: {target.apk}")
    r = _adb(serial, "shell", "pm", "path", target.package, timeout=15)
    if r.returncode == 0 and r.stdout.strip():
        return False
    install = _adb(serial, "install", "-r", str(target.apk), timeout=180)
    if install.returncode != 0:
        raise XfqError(f"adb install failed: {install.stderr.strip() or install.stdout.strip()}")
    return True


def build_run_command(
    target_name: str,
    serial: str | None = None,
    extra_args: list[str] | None = None,
    bundle: Bundle | None = None,
) -> list[str]:
    bundle = bundle or load_active_bundle()
    target = load_recipe(target_name, bundle)
    if not bundle.entry.exists():
        raise XfqError(f"kit entry not found: {bundle.entry}")
    if not target.script.exists():
        raise XfqError(f"sample script not found: {target.script}")
    cmd = [
        sys.executable,
        "-u",
        str(bundle.entry),
        "-p",
        target.package,
        "--script",
        str(target.script),
    ]
    if serial:
        cmd += ["--serial", serial]
    cmd += target.default_args
    if extra_args:
        cmd += extra_args
    return cmd


def run_recipe(
    recipe_name: str,
    serial: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    bundle = load_active_bundle()
    target = load_recipe(recipe_name, bundle)
    installed_apk = False
    if not dry_run:
        installed_apk = ensure_apk_installed(target, serial)
    cmd = build_run_command(target.name, serial=serial, extra_args=extra_args, bundle=bundle)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["XFQTRACE_KIT_ROOT"] = str(bundle.root)
    result: dict[str, Any] = {
        "bundle_version": bundle.version,
        "target": target.name,
        "package": target.package,
        "apk_installed": installed_apk,
        "command": cmd,
        "dry_run": dry_run,
    }
    if dry_run:
        return result
    proc = subprocess.run(cmd, env=env)
    result["returncode"] = proc.returncode
    result["ok"] = proc.returncode == 0
    return result


def list_recipes(bundle: Bundle | None = None) -> list[dict[str, Any]]:
    """List runnable sample directories. Kept name for CLI compatibility."""
    bundle = bundle or load_active_bundle()
    if not bundle.examples_dir.exists():
        return []
    out = []
    for child in sorted(bundle.examples_dir.iterdir()):
        if not child.is_dir():
            continue
        if not (child / DEFAULT_SCRIPT).exists() and not any(child.glob("半自动化trace_*.js")):
            continue
        package = SMOKE_PACKAGE if child.name in {"shp", "shopee"} else child.name
        out.append({"name": child.name, "package": package, "default": package == bundle.default_test or child.name == bundle.default_test})
    return out
