"""
Patch-file infrastructure for Chrono Trigger: Jets of Time.

Phase 1 of the romless-generation migration. The patch shape is now
an APProcedurePatch with a two-step procedure, both steps of which
run on the *player's* machine when they apply the patch via
Patch.py / the AP launcher:

  1. apply_cjot_beta_randomization
     Runs cjot-beta against the player's vanilla CT ROM using the
     seed + flag set the generator embedded in the patch zip.

  2. apply_ctjot_ap_passes
     Applies the six AP-side ROM passes (selective placement,
     validation marker, receive hook, item rename, victory marker,
     classification markers) using the placement table the
     generator embedded in the patch zip.

The generator never reads the vanilla ROM and never invokes
cjot-beta; both move to apply-time so hosts running `Generate.py`
no longer need a CT ROM.

In Phase 1, the two procedure handlers are stubs that raise
NotImplementedError -- bodies land in Phase 3. The generator-side
rewrite (assembling the JSON inputs the handlers will read) lands
in Phase 2.

Between phases the apworld is intentionally non-functional:
generate_output() in __init__.py still constructs the patch via the
old APDeltaPatch-style `patched_path` kwarg, which
CTJoTProcedurePatch does NOT accept, so Generate.py will raise a
TypeError until Phase 2 swaps the call site. That's by design --
"break loudly" is preferable to silently emitting an unappliable
patch.

The vanilla US Chrono Trigger MD5 below matches the unheadered 4 MB
dump that the cjot-beta randomizer also recognizes (see
cjot-beta/sourcefiles/ctrom.py:CTRom.validate_ct_rom_bytes). The
hash is consulted *only at apply time on the player's machine*; the
generator does not load it.
"""
from __future__ import annotations

import hashlib
import os

import Utils
from Utils import read_snes_rom
from worlds.Files import APPatchExtension, APProcedurePatch


# Vanilla unheadered Chrono Trigger (USA) ROM MD5.
CT_USA_HASH = "a2bc447961e52fd2227baed164f729dc"


class CTJoTProcedurePatch(APProcedurePatch):
    """APProcedurePatch wrapper for ctjot.

    Carries the data needed to reproduce a per-player ROM (seed,
    flags, AP placements, slot metadata) inside the patch zip. The
    handlers in CTJoTPatchExtension consume those files at
    apply-time on the player's machine.
    """

    hash = CT_USA_HASH
    game = "Chrono Trigger Jets of Time"
    patch_file_ending = ".apctjot"
    result_file_ending = ".sfc"

    procedure = [
        ("apply_cjot_beta_randomization", ["randomizer_config.json"]),
        ("apply_ctjot_ap_passes", ["ap_placements.json", "ap_metadata.json"]),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()


class CTJoTPatchExtension(APPatchExtension):
    """Apply-time procedure handlers for CTJoTProcedurePatch.

    Auto-registered for `game = "Chrono Trigger Jets of Time"` via
    AutoPatchExtensionRegister; AP's Patch.py looks the handler set
    up by game name and dispatches each procedure step to the
    matching staticmethod here.

    Both staticmethods receive `(caller, rom, *args)` where `caller`
    is the live CTJoTProcedurePatch (used to read embedded files
    via `caller.get_file(name)`) and `rom` is the bytes accumulated
    so far -- the player's vanilla CT for step 1, the cjot-beta
    randomized output for step 2.
    """

    game = "Chrono Trigger Jets of Time"

    @staticmethod
    def apply_cjot_beta_randomization(caller, rom: bytes, config_filename: str) -> bytes:
        """Run cjot-beta against the player's vanilla ROM.

        Materializes `rom` to a tempfile (the cjot-beta CLI takes
        `-i <path>`), invokes the randomizer subprocess with the
        seed + flags from randomizer_config.json, and returns the
        bytes of the produced .sfc.
        """
        import json
        import tempfile
        from pathlib import Path
        from . import randomizer as ctjot_randomizer

        config = json.loads(caller.get_file(config_filename).decode("utf-8"))
        seed = config.get("seed")
        flags = list(config.get("flags") or [])

        cjot_beta_path = _resolve_cjot_beta_path()

        with tempfile.TemporaryDirectory(prefix="ctjot-apply-") as tmpdir_s:
            tmpdir = Path(tmpdir_s)
            vanilla_path = tmpdir / "vanilla.sfc"
            vanilla_path.write_bytes(rom)
            out_dir = tmpdir / "out"
            out_dir.mkdir()

            result = ctjot_randomizer.invoke(
                base_rom_path=vanilla_path,
                output_dir=out_dir,
                cjot_beta_path=cjot_beta_path,
                extra_args=flags,
                seed=seed,
            )
            if not result.success or result.rom_path is None:
                tail = "\n".join(
                    (result.stdout + "\n" + result.stderr).strip().splitlines()[-30:]
                )
                raise RuntimeError(
                    f"cjot-beta randomizer failed (exit {result.returncode}). "
                    f"Tail of its output:\n{tail}"
                )
            return result.rom_path.read_bytes()

    @staticmethod
    def apply_ctjot_ap_passes(
        caller, rom: bytes, placements_filename: str, metadata_filename: str,
    ) -> bytes:
        """Apply the six AP-side ROM passes to the cjot-beta output.

        Loads ap_placements.json + ap_metadata.json, opens `rom`
        (the cjot-beta-randomized bytes from step 1) as a CTRom,
        runs `apply_all_from_records`, finalizes scripts + checksum,
        and returns the final ROM bytes.
        """
        import json
        from . import patches as ctjot_patches

        placements = json.loads(caller.get_file(placements_filename).decode("utf-8"))
        metadata = json.loads(caller.get_file(metadata_filename).decode("utf-8"))

        cjot_beta_path = _resolve_cjot_beta_path()
        ctjot_patches._ensure_beta_on_path(cjot_beta_path)
        from ctrom import CTRom  # type: ignore  # cjot-beta module

        ct_rom = CTRom(rom, ignore_checksum=True)
        ctjot_patches.apply_all_from_records(ct_rom, placements, metadata)
        ct_rom.write_all_scripts_to_rom()
        ct_rom.fix_snes_checksum()

        return bytes(ct_rom.rom_data.getbuffer())


_cached_bundled_beta_path = None  # filled lazily by _resolve_cjot_beta_path


def _resolve_cjot_beta_path():
    """Resolve the cjot-beta source root for apply-time invocation.

    Lookup order:
      1. host.yaml `ctjot_options.cjot_beta_path` if configured AND
         the resulting path actually exists. Treated as a developer /
         power-user override -- mostly relevant for tracking a
         non-bundled cjot-beta checkout.
      2. The `_beta/` tree bundled inside this apworld
         (worlds/ctjot/_beta/sourcefiles/randomizer.py). This is the
         normal path for end users -- it requires no separate
         install of cjot-beta.

    Two flavors of (2) depending on how the apworld was loaded:
      - Unpacked: `worlds/ctjot/` is a real directory; the bundle
        is read directly from it.
      - Zipped (`.apworld`): the bundle lives inside the zip and
        the cjot-beta randomizer subprocess needs real filesystem
        paths, so on first call we extract `_beta/` to a tempdir
        and cache the path. The tempdir is cleaned up at process
        exit via atexit.
    """
    from pathlib import Path

    options = Utils.get_options()
    configured = options.get("ctjot_options", {}).get("cjot_beta_path") or ""
    if configured:
        p = str(configured)
        if not os.path.exists(p):
            p = Utils.user_path(p)
        candidate = Path(p)
        if (candidate / "sourcefiles" / "randomizer.py").exists() or \
           (candidate.name == "sourcefiles" and (candidate / "randomizer.py").exists()):
            return candidate

    return _resolve_bundled_cjot_beta()


def _resolve_bundled_cjot_beta():
    """Locate the bundled `_beta/` tree, extracting from the apworld
    zip on demand if the apworld is loaded as a `.apworld` zip.
    """
    global _cached_bundled_beta_path
    from pathlib import Path

    if _cached_bundled_beta_path is not None:
        return _cached_bundled_beta_path

    bundled = Path(__file__).parent / "_beta"
    if (bundled / "sourcefiles" / "randomizer.py").exists():
        _cached_bundled_beta_path = bundled
        return bundled

    # Apworld is loaded from a zip -- find the .apworld file by
    # walking up __file__'s parents and extract _beta/.
    apworld_zip = None
    for parent in Path(__file__).parents:
        if parent.suffix == ".apworld":
            apworld_zip = parent
            break
    if apworld_zip is None or not apworld_zip.is_file():
        raise RuntimeError(
            "ctjot bundled cjot-beta is missing: neither an unpacked "
            f"_beta/ at {bundled} nor a parent .apworld zip was found."
        )

    import atexit
    import tempfile
    import zipfile

    tmpdir_obj = tempfile.TemporaryDirectory(prefix="ctjot-beta-")
    atexit.register(tmpdir_obj.cleanup)
    tmproot = Path(tmpdir_obj.name)

    with zipfile.ZipFile(str(apworld_zip)) as zf:
        # Apworld zips namespace entries under "<world>/...".
        # `worlds.ctjot` resolves to ".../<world>/__init__.py", so
        # the top-level prefix inside the zip is the world folder
        # name (typically "ctjot").
        world_prefix = Path(__file__).parent.name
        beta_prefix = f"{world_prefix}/_beta/"
        any_extracted = False
        for name in zf.namelist():
            if not name.startswith(beta_prefix) or name.endswith("/"):
                continue
            rel = name[len(world_prefix) + 1:]   # strip "<world>/"
            target = tmproot / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            any_extracted = True

    extracted = tmproot / "_beta"
    if not any_extracted or not (extracted / "sourcefiles" / "randomizer.py").exists():
        raise RuntimeError(
            f"ctjot apworld at {apworld_zip} does not contain a usable "
            "_beta/sourcefiles/ tree."
        )

    _cached_bundled_beta_path = extracted
    return extracted


def get_base_rom_bytes(file_name: str = "") -> bytes:
    """Read the user's vanilla CT ROM (cached) and assert its MD5."""
    base_rom_bytes = getattr(get_base_rom_bytes, "base_rom_bytes", None)
    if base_rom_bytes:
        return base_rom_bytes

    file_name = get_base_rom_path(file_name)
    base_rom_bytes = bytes(read_snes_rom(open(file_name, "rb")))

    basemd5 = hashlib.md5()
    basemd5.update(base_rom_bytes)
    if CT_USA_HASH != basemd5.hexdigest():
        raise Exception(
            "Supplied Chrono Trigger ROM does not match the known MD5 for "
            "the unheadered US release "
            f"(expected {CT_USA_HASH}, got {basemd5.hexdigest()}). "
            "Make sure you are providing a clean dump of the original cart."
        )
    get_base_rom_bytes.base_rom_bytes = base_rom_bytes  # type: ignore[attr-defined]
    return base_rom_bytes


def get_base_rom_path(file_name: str = "") -> str:
    """Resolve the on-disk path to the user's vanilla CT ROM via host.yaml."""
    options = Utils.get_options()
    if not file_name:
        file_name = options["ctjot_options"]["rom_file"]
    if not os.path.exists(file_name):
        file_name = Utils.user_path(file_name)
    return file_name
