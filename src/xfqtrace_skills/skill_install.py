from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .paths import SkillTarget, skill_targets

SKILL_NAME = "xfqtrace-workflow"


@dataclass
class SkillStatus:
    target: str
    path: Path
    installed: bool
    points_to: str | None = None


def bundled_skill_path() -> Path:
    return Path(str(resources.files("xfqtrace_skills").joinpath("skills", SKILL_NAME)))


def _install_one(target: SkillTarget, mode: str = "symlink", force: bool = False) -> SkillStatus:
    src = bundled_skill_path()
    dst = target.path / SKILL_NAME
    target.path.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if not force:
            return status_one(target)
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if mode == "copy":
        shutil.copytree(src, dst)
    else:
        try:
            dst.symlink_to(src, target_is_directory=True)
        except OSError:
            shutil.copytree(src, dst)
    return status_one(target)


def install_skill(target: str = "both", mode: str = "symlink", force: bool = False) -> list[SkillStatus]:
    targets = skill_targets()
    names = ["claude", "codex"] if target == "both" else [target]
    bad = [n for n in names if n not in targets]
    if bad:
        raise ValueError(f"unknown skill target: {', '.join(bad)}")
    return [_install_one(targets[n], mode=mode, force=force) for n in names]


def status_one(target: SkillTarget) -> SkillStatus:
    dst = target.path / SKILL_NAME
    points_to = None
    if dst.is_symlink():
        try:
            points_to = str(dst.resolve())
        except OSError:
            points_to = "<broken symlink>"
    elif dst.exists():
        points_to = str(dst)
    return SkillStatus(target=target.name, path=dst, installed=dst.exists(), points_to=points_to)


def skill_status(target: str = "both") -> list[SkillStatus]:
    targets = skill_targets()
    names = ["claude", "codex"] if target == "both" else [target]
    bad = [n for n in names if n not in targets]
    if bad:
        raise ValueError(f"unknown skill target: {', '.join(bad)}")
    return [status_one(targets[n]) for n in names]
