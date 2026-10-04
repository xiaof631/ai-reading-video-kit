"""Keep configuration-provided filenames inside the selected output directory.

These local CLI tools assume trusted directories; this is not a sandbox against
another process replacing files or symlinks concurrently.
"""
from pathlib import Path


def child_path(directory, name):
    if (not isinstance(name, str) or not name or name in (".", "..")
            or any(c in name for c in ("/", "\\", ":", "\x00"))
            or any(ord(c) < 32 for c in name)):
        raise ValueError("配置中的文件名必须是单个名称，不能包含路径或控制字符")
    root = Path(directory).resolve()
    candidate = root / name
    # Also reject existing symlinks, even ones pointing inside the root.
    if candidate.is_symlink() or candidate.resolve().parent != root:
        raise ValueError("配置文件路径不能指向符号链接或目录外部")
    return candidate
