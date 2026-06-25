from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "xfq"
DATA_APP_NAME = "xfqtrace"
CONFIG_FILE = "config.json"
INSTALL_ROOT_KEY = "install_root"


def home() -> Path:
    return Path.home()


def _windows_local_appdata() -> Path:
    if value := os.environ.get("LOCALAPPDATA"):
        return Path(value).expanduser()
    return home() / "AppData" / "Local"


def data_root() -> Path:
    if value := os.environ.get("XFQTRACE_HOME"):
        return Path(value).expanduser().resolve()
    cfg = read_config()
    if value := cfg.get(INSTALL_ROOT_KEY):
        p = Path(value).expanduser().resolve()
        if p:
            return p
    if platform.system().lower() == "windows":
        return _windows_local_appdata() / DATA_APP_NAME
    if value := os.environ.get("XDG_DATA_HOME"):
        return Path(value).expanduser() / DATA_APP_NAME
    return home() / ".local" / "share" / DATA_APP_NAME


def config_dir() -> Path:
    if value := os.environ.get("XFQ_CONFIG_HOME"):
        return Path(value).expanduser().resolve()
    if platform.system().lower() == "windows":
        return _windows_local_appdata() / APP_NAME
    if value := os.environ.get("XDG_CONFIG_HOME"):
        return Path(value).expanduser() / APP_NAME
    return home() / ".config" / APP_NAME


def versions_dir() -> Path:
    return data_root() / "versions"


def current_link() -> Path:
    return data_root() / "current"


def config_path() -> Path:
    return config_dir() / CONFIG_FILE


def ensure_base_dirs() -> None:
    versions_dir().mkdir(parents=True, exist_ok=True)
    config_dir().mkdir(parents=True, exist_ok=True)


def read_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(config: dict) -> None:
    ensure_base_dirs()
    config_path().write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_install_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    cfg = read_config()
    cfg[INSTALL_ROOT_KEY] = str(root)
    write_config(cfg)
    return root


def set_active_bundle(version: str, path: Path) -> None:
    ensure_base_dirs()
    link = current_link()
    if link.exists() or link.is_symlink():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    try:
        link.symlink_to(path, target_is_directory=True)
    except OSError:
        # Windows or restricted FS fallback: keep config authoritative.
        pass
    cfg = read_config()
    cfg.update({"active_version": version, "active_root": str(path)})
    write_config(cfg)


def active_root() -> Path | None:
    cfg = read_config()
    if value := cfg.get("active_root"):
        p = Path(value).expanduser()
        if p.exists():
            return p
    link = current_link()
    if link.exists():
        return link.resolve()
    return None


@dataclass(frozen=True)
class SkillTarget:
    name: str
    path: Path


def skill_targets() -> dict[str, SkillTarget]:
    return {
        "claude": SkillTarget("claude", home() / ".claude" / "skills"),
        "codex": SkillTarget("codex", home() / ".codex" / "skills"),
    }
