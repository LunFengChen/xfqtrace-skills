from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .bundle import XfqError, bundle_tool_status, install_bundle, list_versions, load_active_bundle, use_version
from .doctor import doctor, print_human_doctor
from .paths import read_config, write_config, data_root, config_dir, versions_dir, current_link, config_path, set_install_root
from .runner import list_recipes, run_recipe
from .skill_install import install_skill, skill_status
from .update_check import fetch_channel, fetch_remote_channel, newer

app = typer.Typer(name="xfq", help="xfQTrace kit 安装、运行和智能体技能工具", no_args_is_help=True)
skill_app = typer.Typer(name="skill", help="安装/查看 Claude/Codex 技能", no_args_is_help=True)
app.add_typer(skill_app, name="skill")
console = Console()
err_console = Console(stderr=True)


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _truthy(value: str) -> bool | None:
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def _auto_update_enabled() -> bool:
    if os.environ.get("XFQ_SKIP_AUTO_UPDATE") == "1":
        return False
    return read_config().get("auto_update_check", True) is not False


def _pipx_like_install() -> bool:
    parts = {p.lower() for p in Path(sys.executable).parts}
    return "pipx" in parts and "xfqtrace-skills" in parts


def _update_command() -> list[str]:
    if _pipx_like_install() and shutil.which("pipx"):
        return ["pipx", "upgrade", "xfqtrace-skills"]
    return [sys.executable, "-m", "pip", "install", "--upgrade", "xfqtrace-skills"]


def _refresh_skill_command(target: str = "both") -> list[str]:
    return [sys.executable, "-m", "xfqtrace_skills.cli", "skill", "install", "--target", target, "--force"]


def _run_streamed(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    console.print("[cyan]$[/cyan] " + " ".join(cmd))
    return subprocess.call(cmd, env=env)


def _run_self_update(latest_cli: str | None, *, target: str = "both", reinstall_skill: bool = True) -> bool:
    if latest_cli:
        console.print(f"[yellow]准备更新 xfqtrace-skills 到 {latest_cli}[/yellow]")
    rc = _run_streamed(_update_command())
    if rc != 0:
        err_console.print(f"[red]更新失败[/red]: updater exit code {rc}")
        return False
    if reinstall_skill:
        env = os.environ.copy()
        env["XFQ_SKIP_AUTO_UPDATE"] = "1"
        rc = _run_streamed(_refresh_skill_command(target=target), env=env)
        if rc != 0:
            err_console.print(f"[red]技能刷新失败[/red]: skill install exit code {rc}")
            return False
    console.print("[green]xfqtrace-skills 更新完成，Codex/Claude 技能已刷新[/green]")
    return True


def _prompt_cli_update(latest_cli: str | None) -> None:
    if not latest_cli:
        return
    if not sys.stdin.isatty():
        err_console.print(
            f"[yellow]xfqtrace-skills 有新版本[/yellow]: {latest_cli}，可运行 `xfq update` 更新并刷新 Codex/Claude 技能"
        )
        return
    if typer.confirm(f"xfqtrace-skills 有新版本 {latest_cli}，是否现在更新并刷新 Codex/Claude 技能？", default=False):
        _run_self_update(latest_cli, target="both", reinstall_skill=True)
    else:
        err_console.print("[yellow]已跳过本次 xfqtrace-skills 更新[/yellow]")


def _auto_update_check() -> None:
    if not _auto_update_enabled():
        return
    channel, err = fetch_remote_channel(timeout=0.8)
    if not channel:
        return
    try:
        bundle = load_active_bundle()
        bundle_version = bundle.version
        engine_version = str(bundle.manifest.get("engine_version") or bundle.version)
    except XfqError:
        bundle_version = None
        engine_version = None

    latest_bundle = channel.get("latest_bundle_version")
    latest_engine = channel.get("latest_engine_version")
    if newer(latest_engine, engine_version) or newer(latest_bundle, bundle_version):
        err_console.print(
            f"[yellow]xfQTrace kit 有新版本[/yellow]: {latest_bundle or latest_engine}，请进入 x1a0f3n9 知识星球下载最新版，然后运行 `xfq init <zip> -p <password>`"
        )
        return

    latest_cli = channel.get("cli_version")
    if newer(latest_cli, __version__):
        _prompt_cli_update(str(latest_cli))


@app.callback()
def main(ctx: typer.Context):
    """xfQTrace kit 安装、运行和智能体技能工具."""
    if ctx.resilient_parsing or ctx.invoked_subcommand in {None, "set", "update"}:
        return
    _auto_update_check()


@app.command(name="set")
def set_cmd(
    key: str = typer.Argument(..., help="设置项，例如 auto-update-check"),
    value: str = typer.Argument(..., help="on/off"),
):
    """设置 xfq 选项。"""
    normalized = key.strip().lower().replace("_", "-")
    if normalized not in {"auto-update-check", "update-check"}:
        err_console.print("[red]error:[/red] unknown setting. supported: auto-update-check")
        raise typer.Exit(1)
    enabled = _truthy(value)
    if enabled is None:
        err_console.print("[red]error:[/red] value must be on/off")
        raise typer.Exit(1)
    cfg = read_config()
    cfg["auto_update_check"] = enabled
    write_config(cfg)
    console.print(f"auto-update-check: {'on' if enabled else 'off'}")


@app.command()
def init(
    zip_file: Path = typer.Argument(..., help="xfqtrace-kit zip 路径"),
    password: Optional[str] = typer.Option(None, "-p", "--password", help="zip 密码"),
    install_dir: Optional[Path] = typer.Option(None, "--dir", "--install-dir", help="指定 kit 安装根目录，例如 D:\\\\xfqtrace"),
    force: bool = typer.Option(False, "--force", help="覆盖已安装的同版本 kit"),
):
    """安装私有 xfqtrace-kit zip 并设为当前版本。"""
    try:
        if install_dir is not None:
            root = set_install_root(install_dir)
            console.print(f"[green]✓ kit 安装根目录已设置[/green]: {root}")
        bundle = install_bundle(zip_file, password=password, force=force)
        console.print(f"[green]✓ xfqtrace-kit {bundle.version} 已安装[/green]")
        console.print(f"   kit 路径: {bundle.root}")
        console.print("   私有 kit zip / 密码请以 x1a0f3n9 知识星球发布为准；公开 xfqtrace-skills 包不包含私有 payload。")
        tools = bundle_tool_status(bundle)
        console.print("   bin 工具检查:")
        for name, item in tools.items():
            status = "✓" if item.get("exists") else ("必缺" if item.get("required") else "可选缺失")
            console.print(f"     {status} {name}: {item.get('path') or '<not found>'}")
        console.print("   接下来: xfq doctor --serial <device>；如设备已装 com.shopee.vn，可运行 xfq run test --serial <device>")
    except XfqError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


@app.command()
def paths(json_output: bool = typer.Option(False, "--json", help="输出 JSON")):
    """查看 xfq/xfqtrace 数据目录和配置目录。"""
    obj = {
        "data_root": str(data_root()),
        "versions_dir": str(versions_dir()),
        "current_link": str(current_link()),
        "config_dir": str(config_dir()),
        "config_path": str(config_path()),
        "home": str(Path.home()),
    }
    if json_output:
        _print_json(obj)
        return
    console.print("[bold]xfQTrace 路径[/bold]")
    console.print(f"  data_root:     {data_root()}")
    console.print(f"    versions:    {versions_dir()}")
    console.print(f"    current:     {current_link()}")
    console.print(f"  config_dir:    {config_dir()}")
    console.print(f"  config_file:   {config_path()}")
    console.print(f"  home:          {Path.home()}")
    console.print()
    console.print("  这些路径可以通过 XFQTRACE_HOME/XFQ_CONFIG_HOME 环境变量覆盖。")
    console.print("  Windows 如需把 kit 放到 D 盘，可用: xfq init <zip> --dir D:\\\\xfqtrace")
    console.print("  doctor 只检查环境；清理本地 trace/旧 kit 请用 xfq clean。")


@app.command()
def clean(
    version: Optional[str] = typer.Option(None, "--version", help="删除指定已安装 kit 版本"),
    all_versions: bool = typer.Option(False, "--all-versions", help="删除所有旧 kit 版本（保留当前版本）"),
    traces: bool = typer.Option(False, "--traces", help="清理 kit/examples 下的本地 trace 日志目录"),
    yes: bool = typer.Option(False, "-y", "--yes", help="不询问确认"),
):
    """清理本地 xfq trace 产物和已安装 kit 版本。"""
    v_dir = versions_dir()
    if version and not (v_dir / version).exists():
        err_console.print(f"[red]版本未安装: {version}[/red]")
        raise typer.Exit(1)

    if traces:
        try:
            bundle = load_active_bundle()
        except XfqError:
            bundle = None
        if bundle and bundle.examples_dir.exists():
            found = 0
            for child in sorted(bundle.examples_dir.iterdir()):
                logs_dir = child / "xfqtrace_logs"
                if logs_dir.exists() and logs_dir.is_dir():
                    if not yes:
                        if typer.confirm(f"清除 {logs_dir} 下的所有 trace 日志?", default=False):
                            shutil.rmtree(logs_dir)
                            console.print(f"  [yellow]cleaned:[/yellow] {logs_dir}")
                            found += 1
                    else:
                        shutil.rmtree(logs_dir)
                        console.print(f"  [yellow]cleaned:[/yellow] {logs_dir}")
                        found += 1
            if found == 0:
                console.print("[green]没有找到本地 trace 日志[/green]")
        else:
            console.print("[green]没有找到本地 trace 日志[/green]")
        console.print("说明: xfq clean --traces 只清理本机 kit/examples/*/xfqtrace_logs，不会清设备 /sdcard 或 app data。")

    if all_versions or version:
        if not v_dir.exists():
            console.print("[green]没有已安装的 kit 版本[/green]")
            return
        try:
            active = load_active_bundle().version
        except XfqError:
            active = None
        targets = [version] if version else [p.name for p in v_dir.iterdir() if p.is_dir() and p.name != active]
        if not targets:
            console.print("[green]没有可删除的旧版本[/green]")
            return
        if not yes:
            if not typer.confirm(f"删除以下版本: {', '.join(targets)}?", default=False):
                console.print("已取消")
                return
        for v in targets:
            target_path = v_dir / v
            if target_path.exists():
                shutil.rmtree(target_path)
                console.print(f"  [yellow]removed:[/yellow] {v}")
    # end def clean


@app.command()
def info(json_output: bool = typer.Option(False, "--json", help="输出 JSON")):
    """查看当前 kit 和样本。"""
    try:
        bundle = load_active_bundle()
        obj = {
            "bundle_version": bundle.version,
            "root": str(bundle.root),
            "manifest": bundle.manifest,
            "samples": list_recipes(bundle),
            "installed_versions": list_versions(),
        }
        if json_output:
            _print_json(obj)
            return
        table = Table(title="xfQTrace kit")
        table.add_column("key")
        table.add_column("value")
        table.add_row("version", bundle.version)
        table.add_row("root", str(bundle.root))
        table.add_row("default_test", bundle.default_test)
        console.print(table)
        if obj["samples"]:
            rt = Table(title="samples")
            rt.add_column("name")
            rt.add_column("package")
            rt.add_column("default")
            for r in obj["samples"]:
                rt.add_row(str(r.get("name")), str(r.get("package")), "yes" if r.get("default") else "")
            console.print(rt)
    except XfqError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


@app.command()
def version(json_output: bool = typer.Option(False, "--json", help="输出 JSON"), check: bool = typer.Option(True, "--check/--no-check", help="检查更新通道")):
    """查看 CLI 和当前 kit 版本。"""
    try:
        bundle = load_active_bundle()
        bundle_version = bundle.version
    except XfqError:
        bundle_version = None
    channel = fetch_channel() if check else {}
    obj = {
        "xfq_cli_version": __version__,
        "active_bundle_version": bundle_version,
        "channel": channel,
        "cli_update_available": newer(channel.get("cli_version"), __version__) if channel else False,
        "bundle_update_available": newer(channel.get("latest_bundle_version"), bundle_version) if channel else False,
    }
    if json_output:
        _print_json(obj)
        return
    console.print(f"xfq cli: {__version__}")
    console.print(f"active kit: {bundle_version or '<not installed>'}")
    if channel:
        console.print(f"latest known kit: {channel.get('latest_bundle_version')}")
        if obj["bundle_update_available"]:
            console.print(f"[yellow]update:[/yellow] {channel.get('download_hint')}")
        if obj["cli_update_available"]:
            console.print("[yellow]cli update:[/yellow] xfq update")


@app.command()
def update(
    yes: bool = typer.Option(False, "-y", "--yes", help="不询问确认"),
    target: str = typer.Option("both", "--target", help="claude|codex|both"),
    reinstall_skill: bool = typer.Option(True, "--install-skill/--no-install-skill", help="更新后刷新已安装 Codex/Claude 技能"),
    force: bool = typer.Option(False, "--force", help="即使通道未报告新版本也强制运行更新器"),
):
    """更新 xfqtrace-skills 包并刷新已安装技能。"""
    channel = fetch_channel()
    latest_cli = channel.get("cli_version")
    if not force and not newer(latest_cli, __version__):
        console.print(f"[green]xfqtrace-skills 已是最新[/green]: {__version__}")
        if reinstall_skill:
            env = os.environ.copy()
            env["XFQ_SKIP_AUTO_UPDATE"] = "1"
            rc = _run_streamed(_refresh_skill_command(target=target), env=env)
            if rc != 0:
                raise typer.Exit(rc)
        return
    if not yes and not typer.confirm(f"是否更新 xfqtrace-skills 到 {latest_cli or 'latest'} 并刷新技能？", default=False):
        console.print("已取消更新")
        return
    if not _run_self_update(str(latest_cli) if latest_cli else None, target=target, reinstall_skill=reinstall_skill):
        raise typer.Exit(1)


@app.command(name="doctor")
def doctor_cmd(
    serial: Optional[str] = typer.Option(None, "--serial", "--device", help="ADB 设备序列号"),
    install_kpm: bool = typer.Option(False, "--install-kpm", help="如 KPM 未安装，则尝试 push/load kit/bin/xfvmahide.kpm"),
    kpm_superkey: Optional[str] = typer.Option(None, "--kpm-superkey", help="APatch/KernelPatch superkey；也可用 XFQ_KPM_SUPERKEY"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON"),
):
    """检查 kit、Python、adb/frida、设备和技能状态。"""
    result = doctor(
        serial=serial,
        install_kpm=install_kpm,
        kpm_superkey=kpm_superkey or os.environ.get("XFQ_KPM_SUPERKEY"),
    )
    if json_output:
        _print_json(result)
        return
    console.print(print_human_doctor(result))

@app.command()
def use(version: str = typer.Argument(..., help="已安装 kit 版本")):
    """切换当前 xfqtrace-kit 版本。"""
    try:
        bundle = use_version(version)
        console.print(f"[green]Current kit -> {bundle.version}[/green]")
    except XfqError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="test 或样本包名"),
    serial: Optional[str] = typer.Option(None, "--serial", "--device", help="ADB 设备序列号"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印命令，不执行"),
):
    """调用 kit 内的 全自动化trace.py 执行 trace。"""
    try:
        result = run_recipe(target, serial=serial, extra_args=list(ctx.args), dry_run=dry_run)
        if dry_run:
            _print_json(result)
        elif not result.get("ok"):
            raise typer.Exit(int(result.get("returncode") or 1))
    except XfqError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


@skill_app.command("install")
def skill_install_cmd(
    target: str = typer.Option("both", "--target", help="claude|codex|both"),
    mode: str = typer.Option("symlink", "--mode", help="symlink|copy"),
    force: bool = typer.Option(False, "--force", help="替换已存在技能"),
):
    """安装内置 xfqtrace-workflow 技能。"""
    try:
        statuses = install_skill(target=target, mode=mode, force=force)
        _print_json([asdict(s) for s in statuses])
    except Exception as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


@skill_app.command("status")
def skill_status_cmd(target: str = typer.Option("both", "--target", help="claude|codex|both")):
    """查看 Claude/Codex 技能安装状态。"""
    try:
        _print_json([asdict(s) for s in skill_status(target=target)])
    except Exception as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
