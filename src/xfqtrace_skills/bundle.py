from __future__ import annotations

import getpass
import json
import platform
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyzipper

from .paths import active_root, ensure_base_dirs, set_active_bundle, versions_dir


class XfqError(RuntimeError):
    pass


@dataclass(frozen=True)
class Bundle:
    root: Path
    manifest: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.manifest.get("bundle_version") or "")

    @property
    def entry(self) -> Path:
        return self.root / str(self.manifest.get("entry", "全自动化trace.py"))

    @property
    def examples_dir(self) -> Path:
        return self.root / "examples"

    @property
    def helpers_dir(self) -> Path:
        return self.root / "helpers"

    @property
    def scripts_dir(self) -> Path:
        # Backward-compatible name for old callers; new kits use helpers/.
        return self.helpers_dir

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def lz4_path(self) -> Path | None:
        if platform.system().lower() == "windows":
            return _first_existing([self.bin_dir / "lz4.exe", self.bin_dir / "lz4"])
        return _first_existing([self.bin_dir / "lz4", self.bin_dir / "lz4.exe"])

    @property
    def pidcat_path(self) -> Path | None:
        if platform.system().lower() == "windows":
            return _first_existing([self.bin_dir / "pidcat.exe", self.bin_dir / "pidcat"])
        return _first_existing([self.bin_dir / "pidcat", self.bin_dir / "pidcat.exe"])

    @property
    def xfvmahide_kpm(self) -> Path:
        return self.bin_dir / "xfvmahide.kpm"

    @property
    def seven_zip_path(self) -> Path | None:
        if platform.system().lower() == "windows":
            return _first_existing([self.bin_dir / "7z.exe", self.bin_dir / "7z"])
        return _first_existing([self.bin_dir / "7z", self.bin_dir / "7z.exe"])


    @property
    def default_test(self) -> str:
        return str(self.manifest.get("default_test", "com.shopee.vn"))


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.exists():
        raise XfqError(f"manifest.json not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise XfqError(f"invalid manifest.json: {exc}") from exc


def load_active_bundle() -> Bundle:
    root = active_root()
    if not root:
        raise XfqError("尚未初始化 xfqtrace-kit，请先运行: xfq init <xfqtrace-kit.zip>")
    return Bundle(root=root, manifest=load_manifest(root))


def validate_bundle_root(root: Path) -> Bundle:
    manifest = load_manifest(root)
    version = str(manifest.get("bundle_version") or "").strip()
    if not version:
        raise XfqError("manifest.bundle_version is required")
    bundle = Bundle(root=root, manifest=manifest)
    required = [
        bundle.bin_dir / "libxfqtrace.so",
        bundle.entry,
        bundle.examples_dir / bundle.default_test / "半自动化trace.js",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        raise XfqError("kit 缺少必要文件: " + ", ".join(missing))
    return bundle


def bundle_tool_status(bundle: Bundle) -> dict[str, Any]:
    """Return checks for the self-contained host/device tools under kit/bin."""
    lib = bundle.bin_dir / "libxfqtrace.so"
    lz4 = bundle.bin_dir / "lz4"
    lz4_exe = bundle.bin_dir / "lz4.exe"
    pidcat = bundle.bin_dir / "pidcat"
    pidcat_exe = bundle.bin_dir / "pidcat.exe"
    seven_zip = bundle.bin_dir / "7z"
    seven_zip_exe = bundle.bin_dir / "7z.exe"
    kpm = bundle.xfvmahide_kpm
    return {
        "libxfqtrace": {"path": str(lib), "exists": lib.exists(), "required": True},
        "lz4": {"path": str(lz4), "exists": lz4.exists(), "required": False},
        "lz4_exe": {"path": str(lz4_exe), "exists": lz4_exe.exists(), "required": False},
        "pidcat": {"path": str(pidcat), "exists": pidcat.exists(), "required": False},
        "pidcat_exe": {"path": str(pidcat_exe), "exists": pidcat_exe.exists(), "required": False},
        "7z": {"path": str(seven_zip), "exists": seven_zip.exists(), "required": False},
        "7z_exe": {"path": str(seven_zip_exe), "exists": seven_zip_exe.exists(), "required": False},
        "xfvmahide_kpm": {"path": str(kpm), "exists": kpm.exists(), "required": False},
    }


def chmod_bundle_tools(bundle: Bundle) -> None:
    """Make installed kit tools executable on Unix-like systems.

    On Windows chmod is harmless but not meaningful; ignore failures because zip
    extraction may land on filesystems that do not support POSIX mode bits.
    """
    for path in [
        bundle.bin_dir / "libxfqtrace.so",
        bundle.bin_dir / "lz4",
        bundle.bin_dir / "lz4.exe",
        bundle.bin_dir / "pidcat",
        bundle.bin_dir / "pidcat.exe",
        bundle.bin_dir / "7z",
        bundle.bin_dir / "7z.exe",
        bundle.bin_dir / "xfvmahide.kpm",
    ]:
        if not path.exists():
            continue
        try:
            path.chmod(path.stat().st_mode | 0o755)
        except OSError:
            pass


def _zip_password(password: str | None) -> bytes | None:
    if password is None:
        password = getpass.getpass("Password for xfqtrace-kit zip (empty if none): ")
    if password == "":
        return None
    return password.encode("utf-8")


def _extract_zip(zip_path: Path, dest: Path, password: bytes | None) -> None:
    # pyzipper supports AES and ZipCrypto.  Fall back to stdlib for plain zips.
    try:
        with pyzipper.AESZipFile(zip_path) as zf:
            if password:
                zf.pwd = password
            zf.extractall(dest)
        return
    except RuntimeError as exc:
        raise XfqError(f"解压失败，可能是密码错误: {exc}") from exc
    except Exception:
        if password:
            raise
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
    except RuntimeError as exc:
        raise XfqError(f"解压失败，可能是密码错误: {exc}") from exc


def _find_extracted_root(dest: Path) -> Path:
    direct = dest / "manifest.json"
    if direct.exists():
        return dest
    dirs = [p for p in dest.iterdir() if p.is_dir()]
    if len(dirs) == 1 and (dirs[0] / "manifest.json").exists():
        return dirs[0]
    for p in dirs:
        if (p / "manifest.json").exists():
            return p
    raise XfqError("压缩包内未找到 manifest.json")


def _ensure_script_compat_links(bundle_root: Path) -> None:
    """Keep legacy scripts/ entry layouts working without reintroducing it for new kits."""
    scripts = bundle_root / "scripts"
    if not scripts.exists():
        return
    links = {
        scripts / "bin": Path("../bin"),
        scripts / "helpers": Path("../helpers"),
        scripts / "scripts": Path("."),
    }
    for link, target in links.items():
        if link.exists() or link.is_symlink():
            continue
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            # Fallback for Windows/restricted FS: copy minimal directories.
            if link.name == "bin" and (bundle_root / "bin").exists():
                shutil.copytree(bundle_root / "bin", link)


def install_bundle(zip_file: str | Path, password: str | None = None, force: bool = False) -> Bundle:
    zip_path = Path(zip_file).expanduser().resolve()
    if not zip_path.exists():
        raise XfqError(f"zip not found: {zip_path}")
    ensure_base_dirs()
    pwd = _zip_password(password)
    with tempfile.TemporaryDirectory(prefix="xfq-kit-") as td:
        tmp = Path(td)
        _extract_zip(zip_path, tmp, pwd)
        extracted = _find_extracted_root(tmp)
        bundle = validate_bundle_root(extracted)
        version = bundle.version
        target = versions_dir() / version
        if target.exists():
            if not force:
                raise XfqError(f"bundle {version} 已存在；如需覆盖请加 --force")
            shutil.rmtree(target)
        shutil.copytree(extracted, target)
    _ensure_script_compat_links(target)
    installed = validate_bundle_root(target)
    chmod_bundle_tools(installed)
    set_active_bundle(installed.version, target)
    return installed


def list_versions() -> list[str]:
    root = versions_dir()
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def use_version(version: str) -> Bundle:
    root = versions_dir() / version
    if not root.exists():
        raise XfqError(f"bundle version not installed: {version}")
    bundle = validate_bundle_root(root)
    set_active_bundle(bundle.version, root)
    return bundle
