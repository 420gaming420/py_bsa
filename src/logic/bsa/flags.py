# BSA archive flag detection — mirrors BSArch DetectFlags
# References: wbBSArchive.pas@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0)

from __future__ import annotations

from logic.bsa.constants import (
    ARCHIVE_COMPRESS,
    ARCHIVE_DEFAULT,
    ARCHIVE_EMBEDNAME,
    ARCHIVE_RETAINNAME,
    ARCHIVE_STARTUPSTR,
    ARCHIVE_XMEM,
    ARCHIVE_UNKNOWN10,
    FILE_FONTS,
    FILE_MESHES,
    FILE_MENUS,
    FILE_MISC,
    FILE_SHADERS,
    FILE_SOUNDS,
    FILE_TEXTURES,
    FILE_TREES,
    FILE_VOICES,
)


# ---------------------------------------------------------------------------
# Asset type classification (mirrors TwbAsset::cBSAssets in wbBSArchive.pas) — TES5Edit@76d9d226
# ---------------------------------------------------------------------------

_ASSET_ROOTS: list[tuple[str, int]] = [
    ("meshes",      FILE_MESHES),
    ("textures",    FILE_TEXTURES),
    ("materials",   FILE_MISC),
    ("geometries",  FILE_MISC),
    ("sound\\voice",FILE_VOICES),
    ("sound",       FILE_SOUNDS),
    ("music",       FILE_SOUNDS),
    ("scripts\\source", FILE_MISC),  # scripts/source → misc
    ("source\\scripts", FILE_MISC),  # source/scripts → misc (SSE)
    ("scripts",     FILE_MISC),
    ("strings",     FILE_SOUNDS),   # strings → sounds flag
    ("trees",       FILE_TREES),
    ("video",       FILE_SOUNDS),
    ("lodsettings", FILE_MESHES | FILE_MISC),
    ("distantlod",  FILE_MESHES | FILE_MISC),
    ("interface",   FILE_SHADERS),
    ("programs",    FILE_SHADERS),
    ("menus",       FILE_MENUS),
    ("fonts",       FILE_FONTS),
    ("facegen",     FILE_MISC),
    ("lsdata",      FILE_MISC),
    ("shaders",     FILE_SHADERS),
    ("shadersfx",   FILE_SHADERS),
    ("grass",       FILE_MISC),
    ("vis",         FILE_MISC),
    ("seq",         FILE_MISC),
    ("dialogueviews", FILE_SHADERS),
]

_ASSET_EXTENSIONS: dict[str, int] = {
    ".nif":     FILE_MESHES,
    ".kf":      FILE_MESHES,
    ".kfm":     FILE_MESHES,
    ".egm":     FILE_MESHES,
    ".egt":     FILE_MESHES,
    ".tri":     FILE_MESHES,
    ".psa":     FILE_MESHES,
    ".hkt":     FILE_MESHES,
    ".hkx":     FILE_MESHES,
    ".ssf":     FILE_MESHES,
    ".btr":     FILE_MESHES,
    ".bto":     FILE_MESHES,
    ".btt":     FILE_MESHES,
    ".dtl":     FILE_MESHES,
    ".dds":     FILE_TEXTURES,
    ".tga":     FILE_TEXTURES,
    ".png":     FILE_TEXTURES,
    ".bgsm":    FILE_MISC,
    ".bgem":    FILE_MISC,
    ".mesh":    FILE_MISC,
    ".lip":     FILE_VOICES,
    ".wav":     FILE_SOUNDS,
    ".xwm":     FILE_SOUNDS,
    ".mp3":     FILE_SOUNDS,
    ".ogg":     FILE_SOUNDS,
    ".fuz":     FILE_SOUNDS,
    ".psc":     FILE_MISC,
    ".pex":     FILE_MISC,
    ".strings": FILE_SOUNDS,
    ".ilstrings": FILE_SOUNDS,
    ".dlstrings": FILE_SOUNDS,
    ".spt":     FILE_TREES,
    ".bik":     FILE_SOUNDS,
    ".bk2":     FILE_SOUNDS,
    ".lodsettings": FILE_MESHES | FILE_MISC,
    ".dlodsettings": FILE_MESHES | FILE_MISC,
    ".lod":     FILE_MESHES | FILE_MISC,
    ".cmp":     FILE_MESHES | FILE_MISC,
    ".swf":     FILE_SHADERS,
    ".htm":     FILE_SHADERS,
    ".txt":     FILE_SHADERS,
    ".scc":     FILE_SHADERS,
    ".bat":     FILE_SHADERS,
    ".fnt":     FILE_FONTS,
    ".tex":     FILE_FONTS,
    ".ctl":     FILE_MISC,
    ".dat":     FILE_MISC,
    ".sdp":     FILE_SHADERS,
    ".fxp":     FILE_SHADERS,
    ".gid":     FILE_MISC,
    ".uvd":     FILE_MISC,
    ".seq":     FILE_MISC,
    ".dds":     FILE_TEXTURES,
    ".tga":     FILE_TEXTURES,
}


def _classify_file(filename: str) -> int:
    """Return file flag bits for a single file path (mirrors BSArch DetectFlags)."""
    # Normalise separators
    path = filename.replace("/", "\\").lower()

    # Check folder roots first (mirrors TwbAsset::AssetTypeByFolder)
    for root, flag in _ASSET_ROOTS:
        if path == root or path.startswith(root + "\\"):
            return flag

    # Fallback: classify by extension
    dot = path.rfind(".")
    if dot >= 0:
        ext = path[dot:]
        if ext in _ASSET_EXTENSIONS:
            return _ASSET_EXTENSIONS[ext]

    return FILE_MISC


def _is_texture_only(files: list[str]) -> bool:
    """True if all files are .dds or .ddx."""
    for f in files:
        lower = f.lower()
        if not (lower.endswith(".dds") or lower.endswith(".ddx")):
            return False
    return True


def detect_flags(fmt: int, files: list[str], compressed: bool = False) -> tuple[int, int]:
    """Detect archive flags and file flags for a set of files.

    Mirrors TwbCustomBSArchive::DetectFlags from wbBSArchive.pas — TES5Edit@76d9d226.

    Args:
        fmt: ArchiveFormat value (TES4=103, FO3=104, SSE=105, etc.)
        files: List of file paths inside the archive.
        compressed: Whether any file in the archive is compressed.

    Returns:
        (archive_flags, file_flags)
    """
    file_flags = 0
    archive_flags = ARCHIVE_DEFAULT

    # TES4 (Oblivion) gets extra default flags
    # Note: EMBEDNAME is only used for FO3/SSE decompression, not TES4
    if fmt == 103:  # ArchiveFormat.TES4
        archive_flags |= ARCHIVE_XMEM | ARCHIVE_UNKNOWN10

    texture_only = _is_texture_only(files) if files else False

    for filename in files:
        asset_flag = _classify_file(filename)
        file_flags |= asset_flag

        # FO3/FNV: always set sounds+voices together
        if fmt == 104:  # ArchiveFormat.FO3
            if asset_flag & (FILE_SOUNDS | FILE_VOICES):
                file_flags |= FILE_SOUNDS | FILE_VOICES

        # TES4: .xml files → FILE_MENUS
        if fmt == 103:
            lower = filename.lower()
            if lower.endswith(".xml"):
                file_flags |= FILE_MENUS

        # Script files → ARCHIVE_RETAINNAME
        if asset_flag == FILE_MISC:
            lower = filename.lower()
            if lower.endswith(".pex") or lower.endswith(".psc"):
                archive_flags |= ARCHIVE_RETAINNAME

    # Final flag adjustments

    # Menus/shaders/fonts are Oblivion-only
    if fmt != 103:  # not TES4
        file_flags &= ~(FILE_MENUS | FILE_SHADERS | FILE_FONTS)

    # Misc flag is not in Skyrim SE
    if fmt == 105:  # ArchiveFormat.SSE
        file_flags &= ~FILE_MISC

    # Embedded names flag for textures-only archives
    # Mirrors wbBSArchive.pas:1205-1207 — TES5Edit@76d9d226
    # Only FO3/SSE actually use embedded names during decompression
    if texture_only and fmt in (104, 105):  # FO3, SSE
        archive_flags |= ARCHIVE_EMBEDNAME

    # Startupstr flag when meshes are present
    if file_flags & FILE_MESHES:
        archive_flags |= ARCHIVE_STARTUPSTR

    # Retainname flag when sounds are present
    if file_flags & FILE_SOUNDS:
        archive_flags |= ARCHIVE_RETAINNAME

    # Compressed flag if at least one file is compressed
    if compressed:
        archive_flags |= ARCHIVE_COMPRESS

    return archive_flags, file_flags
