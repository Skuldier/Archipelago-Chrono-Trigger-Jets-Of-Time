"""
Subprocess wrapper around the cjot-beta randomizer.

Used by CTJoTWorld.generate_output() during AP `Generate.py`. We invoke
the beta randomizer as `python -m randomizer` from inside its own
sourcefiles/ directory so its top-level imports (ctenums, ctrom, etc.)
resolve. The output ROM lands in the supplied `output_dir`; we discover
it by scanning for the .sfc/.smc file that wasn't there before.

This is largely a port of webapp/randomizer.py, restructured to be
callable from inside an apworld's generate_output (no Flask context).
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Hard ceiling on randomizer wall-clock time. Measured ~5s for typical
# seeds on this workstation; 120s is generous.
DEFAULT_TIMEOUT_SEC = 120


class RandomizerError(Exception):
    """Raised when the cjot-beta randomizer can't be invoked or fails."""


@dataclass
class RandomizerResult:
    success: bool
    returncode: int
    rom_path: Optional[Path]
    spoiler_path: Optional[Path]
    flag_string: str
    stdout: str
    stderr: str


def resolve_beta_root(cjot_beta_path: Path) -> Path:
    """Validate that `cjot_beta_path` looks like a real beta source root.

    Accepts either the project root (containing `sourcefiles/`) or the
    `sourcefiles/` directory itself, and returns the project root.
    """
    cjot_beta_path = Path(cjot_beta_path).resolve()
    if (cjot_beta_path / "sourcefiles" / "randomizer.py").exists():
        return cjot_beta_path
    if cjot_beta_path.name == "sourcefiles" and (cjot_beta_path / "randomizer.py").exists():
        return cjot_beta_path.parent
    raise RandomizerError(
        f"cjot-beta randomizer not found at {cjot_beta_path!s}. "
        "Set ctjot_options.cjot_beta_path in host.yaml to the directory "
        "that contains sourcefiles/randomizer.py."
    )


def invoke(
    base_rom_path: Path,
    output_dir: Path,
    cjot_beta_path: Path,
    extra_args: Optional[list[str]] = None,
    seed: Optional[str] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> RandomizerResult:
    """Run cjot-beta once, dropping the patched ROM into `output_dir`.

    Caller is responsible for cleaning up `output_dir` afterward. The
    resulting RandomizerResult.rom_path is the absolute path to the
    .sfc the beta produced; it lives inside `output_dir`.
    """
    if not base_rom_path.exists():
        raise RandomizerError(f"Base ROM not found at {base_rom_path}")

    project_root = resolve_beta_root(cjot_beta_path)
    sourcefiles = project_root / "sourcefiles"
    randomizer_script = sourcefiles / "randomizer.py"

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        "python",
        "-u",
        str(randomizer_script.name),
        "-i", str(base_rom_path),
        "-o", str(output_dir),
    ]
    if seed:
        cmd.extend(["--seed", seed])
    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(sourcefiles) + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(sourcefiles),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RandomizerError(
            f"cjot-beta randomizer timed out after {timeout_sec}s"
        ) from exc
    except OSError as exc:
        raise RandomizerError(f"Failed to launch randomizer: {exc}") from exc

    rom_path, spoiler_path, flag_string = _discover_outputs(output_dir)

    return RandomizerResult(
        success=(proc.returncode == 0 and rom_path is not None),
        returncode=proc.returncode,
        rom_path=rom_path,
        spoiler_path=spoiler_path,
        flag_string=flag_string,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _discover_outputs(output_dir: Path) -> tuple[Optional[Path], Optional[Path], str]:
    """Locate the .sfc + optional spoiler the randomizer just wrote.

    The beta names files like:
        <input-rom-stem>.<mode>.<diff>.<flags>.<seed>.sfc
        <input-rom-stem>.<mode>.<diff>.<flags>.<seed>.spoilers.txt
    """
    rom_path: Optional[Path] = None
    spoiler_path: Optional[Path] = None
    flag_string = ""

    for p in sorted(output_dir.iterdir()):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in (".sfc", ".smc") and rom_path is None:
            rom_path = p
        elif suf == ".txt" and spoiler_path is None:
            spoiler_path = p

    if rom_path is not None:
        # The flag code is a substring of the output filename's stem.
        # Strip the input-ROM prefix and trailing .sfc; everything left
        # is "<mode>.<diff>.<flags>.<seed>".
        stem = rom_path.stem
        parts = stem.split(".")
        _MODE_TOKENS = {"st", "lw", "ia", "loc", "van"}
        for i, p in enumerate(parts):
            if p in _MODE_TOKENS:
                flag_string = ".".join(parts[i:])
                break

    return rom_path, spoiler_path, flag_string
