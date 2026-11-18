# BSA hash functions

from __future__ import annotations


class TES3Hash:
    """Hash function for TES3 / Morrowind BSA files.

    The hash is a 64-bit value composed of two 32-bit halves:
      - lo: XOR of first-half bytes into rotating 32-bit slots
      - hi: XOR-then-rotate of second-half bytes
    """

    @staticmethod
    def hash(path: str) -> int:
        """Return the 64-bit hash for *path*."""
        s = path.lower().replace("/", "\\")
        mid = len(s) // 2

        lo = 0
        for i in range(mid):
            lo ^= ord(s[i]) << ((i % 4) * 8)

        hi = 0
        for i in range(mid, len(s)):
            idx = i - mid
            rot = ord(s[i]) << ((idx % 4) * 8)
            val = hi ^ rot
            rot_eff = rot & 0x1F
            if rot_eff:
                hi = ((val >> rot_eff) | (val << (32 - rot_eff))) & 0xFFFFFFFF
            else:
                hi = val

        return lo | (hi << 32)


class TES4Hash:
    """Hash function for TES4-like BSA files (v103 / v104 / v105).

    Two entry points:
      - hash_directory(path) — hashes a full directory path
      - hash_file(path) — hashes a filename (path is stripped first)
    """

    _EXT_LUT = ("", ".nif", ".kf", ".dds", ".wav", ".adp")

    @staticmethod
    def _crc32_custom(data: bytes) -> int:
        """Custom CRC-like hash: crc = byte + crc * 0x1003F (mod 2^32)."""
        crc = 0
        for b in data:
            crc = (b + crc * 0x1003F) & 0xFFFFFFFF
        return crc

    @staticmethod
    def hash_directory(path: str, signed: bool = False) -> int:
        """Hash a directory path.

        Mirrors bsa::detail::normalize_path:
        - lowercases and normalises slashes to backslashes
        - strips trailing/leading backslashes
        - if empty or >= 260 chars, replaces with "."
        """
        s = path.lower().replace("/", "\\")
        while s and s[-1] == "\\":
            s = s[:-1]
        while s and s[0] == "\\":
            s = s[1:]
        if not s or len(s) >= 260:
            s = "."

        n = len(s)
        last = ord(s[-1])
        last2 = ord(s[-2]) if n >= 2 else 0
        first = ord(s[0])
        crc = TES4Hash._crc32_custom(s[1 : n - 2].encode("ascii")) if n > 3 else 0

        return (
            (last & 0xFF)
            | ((last2 & 0xFF) << 8)
            | ((n & 0xFF) << 16)
            | ((first & 0xFF) << 24)
            | (crc << 32)
        )

    @staticmethod
    def hash_file(path: str, signed: bool = False) -> int:
        """Hash a file entry. The path component is stripped; only the filename is hashed."""
        s = path.lower().replace("/", "\\")
        sep = s.rfind("\\")
        if sep != -1:
            s = s[sep + 1 :]

        dot = s.rfind(".")
        if dot != -1:
            stem = s[:dot]
            ext = s[dot:]
        else:
            stem = s
            ext = ""

        if not stem or len(stem) >= 260 or len(ext) >= 16:
            return 0

        h = TES4Hash.hash_directory(stem, signed=signed)
        crc_stem = h >> 32
        crc_ext = TES4Hash._crc32_custom(ext.encode("ascii"))
        crc = (crc_stem + crc_ext) & 0xFFFFFFFF

        ext_idx = -1
        for idx, ext_tag in enumerate(TES4Hash._EXT_LUT):
            if ext == ext_tag:
                ext_idx = idx
                break

        if ext_idx >= 0:
            first = ((h >> 24) & 0xFF)
            last = h & 0xFF
            last2 = (h >> 8) & 0xFF

            first = (first + 32 * (ext_idx & 0xFC)) & 0xFF
            last = (last + ((ext_idx & 0xFE) << 6)) & 0xFF
            last2 = (last2 + (ext_idx << 7)) & 0xFF

            h = (
                (last & 0xFF)
                | ((last2 & 0xFF) << 8)
                | ((len(stem) & 0xFF) << 16)
                | (first << 24)
                | (crc << 32)
            )
        else:
            length = len(stem)
            first = (h >> 24) & 0xFF
            last = h & 0xFF
            last2 = (h >> 8) & 0xFF

            h = (
                (last & 0xFF)
                | ((last2 & 0xFF) << 8)
                | ((length & 0xFF) << 16)
                | (first << 24)
                | (crc << 32)
            )

        return h & 0xFFFFFFFFFFFFFFFF

    @classmethod
    def hash_file_signed(cls, path: str) -> int:
        """Hash a filename using signed mode (TES4/Oblivion)."""
        return cls._hash_file_signed_internal(path)

    @staticmethod
    def _hash_file_signed_internal(path: str) -> int:
        """Internal signed hash for TES4 Oblivion format."""
        s = path.lower().replace("/", "\\")
        sep = s.rfind("\\")
        if sep != -1:
            s = s[sep + 1 :]

        dot = s.rfind(".")
        if dot != -1:
            stem = s[:dot]
            ext = s[dot:]
        else:
            stem = s
            ext = ""

        if not stem or len(stem) >= 260 or len(ext) >= 16:
            return 0

        # Hash stem with signed mode
        h_stem = TES4Hash._hash_signed_inner(stem)
        # Hash ext with signed mode
        h_ext = TES4Hash._hash_signed_inner(ext) if ext else 0
        crc = (h_stem >> 32 + h_ext >> 32) & 0xFFFFFFFF
        # Reconstruct with signed adjustments
        crc_stem = TES4Hash._crc32_custom_signed(stem.encode("ascii"))
        crc_ext = TES4Hash._crc32_custom_signed(ext.encode("ascii")) if ext else 0
        crc = (crc_stem + crc_ext) & 0xFFFFFFFF

        # Build lower 32 bits with signed first/last
        n = len(stem)
        last = ord(stem[-1]) if n > 0 else 0
        last2 = ord(stem[-2]) if n >= 2 else 0
        first = ord(stem[0]) if n > 0 else 0

        # Apply extension modifications if applicable
        ext_idx = -1
        for idx, ext_tag in enumerate(TES4Hash._EXT_LUT):
            if ext == ext_tag:
                ext_idx = idx
                break

        if ext_idx >= 0:
            first = (first + 32 * (ext_idx & 0xFC)) & 0xFF
            last = ((last + (ext_idx & 0xFE)) << 6) & 0xFF
            last2 = ((last2 + ext_idx) << 7) & 0xFF

        return (
            (last & 0xFF)
            | ((last2 & 0xFF) << 8)
            | ((n & 0xFF) << 16)
            | (first << 24)
            | (crc << 32)
        ) & 0xFFFFFFFFFFFFFFFF

    @staticmethod
    def _crc32_custom_signed(data: bytes) -> int:
        """Custom CRC-like hash with signed byte correction (TES4/Oblivion)."""
        crc = 0
        for b in data:
            crc = (b + crc * 0x1003F) & 0xFFFFFFFF
            if b > 127:
                crc = (crc - 256) & 0xFFFFFFFF
        return crc

    @staticmethod
    def _hash_signed_inner(stem: str) -> int:
        """Hash a string with signed byte correction for TES4 Oblivion."""
        n = len(stem)
        last = ord(stem[-1]) if n > 0 else 0
        last2 = ord(stem[-2]) if n >= 2 else 0
        first = ord(stem[0]) if n > 0 else 0
        crc = TES4Hash._crc32_custom_signed(stem[1 : n - 2].encode("ascii")) if n > 3 else 0
        return (
            (last & 0xFF)
            | ((last2 & 0xFF) << 8)
            | ((n & 0xFF) << 16)
            | (first << 24)
            | (crc << 32)
        ) & 0xFFFFFFFFFFFFFFFF


class BA2Hash:
    """Hash function for BA2 (Fallout 4) archives.

    Mirrors bsa::fo4::hashing:
    - normalize_path: lowercase, slash->backslash, strip leading/trailing backslashes
    - split_path: parent / stem / extension
    - CRC32 (init=0, no final XOR) on latin-1 bytes for parent and stem
    - Extension stored as raw 4-byte LE u32
    """

    _CRC32_TABLE: tuple[int, ...] = (
        0x00000000, 0x77073096, 0xEE0E612C, 0x990951BA, 0x076DC419, 0x706AF48F,
        0xE963A535, 0x9E6495A3, 0x0EDB8832, 0x79DCB8A4, 0xE0D5E91E, 0x97D2D988,
        0x09B64C2B, 0x7EB17CBD, 0xE7B82D07, 0x90BF1D91, 0x1DB71064, 0x6AB020F2,
        0xF3B97148, 0x84BE41DE, 0x1ADAD47D, 0x6DDDE4EB, 0xF4D4B551, 0x83D385C7,
        0x136C9856, 0x646BA8C0, 0xFD62F97A, 0x8A65C9EC, 0x14015C4F, 0x63066CD9,
        0xFA0F3D63, 0x8D080DF5, 0x3B6E20C8, 0x4C69105E, 0xD56041E4, 0xA2677172,
        0x3C03E4D1, 0x4B04D447, 0xD20D85FD, 0xA50AB56B, 0x35B5A8FA, 0x42B2986C,
        0xDBBBC9D6, 0xACBCF940, 0x32D86CE3, 0x45DF5C75, 0xDCD60DCF, 0xABD13D59,
        0x26D930AC, 0x51DE003A, 0xC8D75180, 0xBFD06116, 0x21B4F4B5, 0x56B3C423,
        0xCFBA9599, 0xB8BDA50F, 0x2802B89E, 0x5F058808, 0xC60CD9B2, 0xB10BE924,
        0x2F6F7C87, 0x58684C11, 0xC1611DAB, 0xB6662D3D, 0x76DC4190, 0x01DB7106,
        0x98D220BC, 0xEFD5102A, 0x71B18589, 0x06B6B51F, 0x9FBFE4A5, 0xE8B8D433,
        0x7807C9A2, 0x0F00F934, 0x9609A88E, 0xE10E9818, 0x7F6A0DBB, 0x086D3D2D,
        0x91646C97, 0xE6635C01, 0x6B6B51F4, 0x1C6C6162, 0x856530D8, 0xF262004E,
        0x6C0695ED, 0x1B01A57B, 0x8208F4C1, 0xF50FC457, 0x65B0D9C6, 0x12B7E950,
        0x8BBEB8EA, 0xFCB9887C, 0x62DD1DDF, 0x15DA2D49, 0x8CD37CF3, 0xFBD44C65,
        0x4DB26158, 0x3AB551CE, 0xA3BC0074, 0xD4BB30E2, 0x4ADFA541, 0x3DD895D7,
        0xA4D1C46D, 0xD3D6F4FB, 0x4369E96A, 0x346ED9FC, 0xAD678846, 0xDA60B8D0,
        0x44042D73, 0x33031DE5, 0xAA0A4C5F, 0xDD0D7CC9, 0x5005713C, 0x270241AA,
        0xBE0B1010, 0xC90C2086, 0x5768B525, 0x206F85B3, 0xB966D409, 0xCE61E49F,
        0x5EDEF90E, 0x29D9C998, 0xB0D09822, 0xC7D7A8B4, 0x59B33D17, 0x2EB40D81,
        0xB7BD5C3B, 0xC0BA6CAD, 0xEDB88320, 0x9ABFB3B6, 0x03B6E20C, 0x74B1D29A,
        0xEAD54739, 0x9DD277AF, 0x04DB2615, 0x73DC1683, 0xE3630B12, 0x94643B84,
        0x0D6D6A3E, 0x7A6A5AA8, 0xE40ECF0B, 0x9309FF9D, 0x0A00AE27, 0x7D079EB1,
        0xF00F9344, 0x8708A3D2, 0x1E01F268, 0x6906C2FE, 0xF762575D, 0x806567CB,
        0x196C3671, 0x6E6B06E7, 0xFED41B76, 0x89D32BE0, 0x10DA7A5A, 0x67DD4ACC,
        0xF9B9DF6F, 0x8EBEEFF9, 0x17B7BE43, 0x60B08ED5, 0xD6D6A3E8, 0xA1D1937E,
        0x38D8C2C4, 0x4FDFF252, 0xD1BB67F1, 0xA6BC5767, 0x3FB506DD, 0x48B2364B,
        0xD80D2BDA, 0xAF0A1B4C, 0x36034AF6, 0x41047A60, 0xDF60EFC3, 0xA867DF55,
        0x316E8EEF, 0x4669BE79, 0xCB61B38C, 0xBC66831A, 0x256FD2A0, 0x5268E236,
        0xCC0C7795, 0xBB0B4703, 0x220216B9, 0x5505262F, 0xC5BA3BBE, 0xB2BD0B28,
        0x2BB45A92, 0x5CB36A04, 0xC2D7FFA7, 0xB5D0CF31, 0x2CD99E8B, 0x5BDEAE1D,
        0x9B64C2B0, 0xEC63F226, 0x756AA39C, 0x026D930A, 0x9C0906A9, 0xEB0E363F,
        0x72076785, 0x05005713, 0x95BF4A82, 0xE2B87A14, 0x7BB12BAE, 0x0CB61B38,
        0x92D28E9B, 0xE5D5BE0D, 0x7CDCEFB7, 0x0BDBDF21, 0x86D3D2D4, 0xF1D4E242,
        0x68DDB3F8, 0x1FDA836E, 0x81BE16CD, 0xF6B9265B, 0x6FB077E1, 0x18B74777,
        0x88085AE6, 0xFF0F6A70, 0x66063BCA, 0x11010B5C, 0x8F659EFF, 0xF862AE69,
        0x616BFFD3, 0x166CCF45, 0xA00AE278, 0xD70DD2EE, 0x4E048354, 0x3903B3C2,
        0xA7672661, 0xD06016F7, 0x4969474D, 0x3E6E77DB, 0xAED16A4A, 0xD9D65ADC,
        0x40DF0B66, 0x37D83BF0, 0xA9BCAE53, 0xDEBB9EC5, 0x47B2CF7F, 0x30B5FFE9,
        0xBDBDF21C, 0xCABAC28A, 0x53B39330, 0x24B4A3A6, 0xBAD03605, 0xCDD70693,
        0x54DE5729, 0x23D967BF, 0xB3667A2E, 0xC4614AB8, 0x5D681B02, 0x2A6F2B94,
        0xB40BBE37, 0xC30C8EA1, 0x5A05DF1B, 0x2D02EF8D,
    )

    @staticmethod
    def _crc32(data: bytes) -> int:
        """Compute standard CRC32 matching bsa C++ reference (init=0, no final XOR) — bsa@b6ab3c8."""
        crc = 0
        for b in data:
            crc = (crc >> 8) ^ BA2Hash._CRC32_TABLE[(crc ^ b) & 0xFF]
        return crc

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path: lowercase, / -> \\, strip leading/trailing \\."""
        s = path.lower().replace("/", "\\")
        while s and s[0] == "\\":
            s = s[1:]
        while s and s[-1] == "\\":
            s = s[:-1]
        return s

    @staticmethod
    def _split_path(path: str) -> tuple[str, str, str]:
        """Split path into (parent, stem, extension) matching bsa C++ — bsa@b6ab3c8."""
        pstem = path.rfind("\\")
        pextension = path.rfind(".")
        if pstem >= 0:
            parent = path[:pstem]
        else:
            parent = ""
        if pextension >= 0:
            extension = path[pextension + 1:]
        else:
            extension = ""
        first = pstem + 1 if pstem >= 0 else 0
        last = pextension - first if pextension >= 0 else len(path) - first
        stem = path[first : first + last]
        return parent, stem, extension

    @staticmethod
    def hash_directory(path: str) -> int:
        """Hash the parent directory portion of a BA2 path."""
        normalized = BA2Hash._normalize_path(path)
        parent, _, _ = BA2Hash._split_path(normalized)
        if not parent:
            return 0
        return BA2Hash._crc32(parent.encode("latin-1"))

    @staticmethod
    def hash_file(path: str) -> int:
        """Hash the stem (filename without extension) of a BA2 path."""
        normalized = BA2Hash._normalize_path(path)
        _, stem, _ = BA2Hash._split_path(normalized)
        if not stem:
            return 0
        return BA2Hash._crc32(stem.encode("latin-1"))

    @staticmethod
    def hash_extension(path: str) -> int:
        """Hash the extension bytes as raw LE u32 (BA2 stores extension as 4 raw bytes)."""
        normalized = BA2Hash._normalize_path(path)
        _, _, ext = BA2Hash._split_path(normalized)
        if not ext:
            return 0
        ext_bytes = ext.encode("ascii")[:4].ljust(4, b"\x00")
        return int.from_bytes(ext_bytes, "little")

    @classmethod
    def compute_full_hash(cls, path: str) -> tuple[int, int, int]:
        """Compute all three BA2 hashes: (directory, file, extension)."""
        normalized = cls._normalize_path(path)
        parent, stem, ext = cls._split_path(normalized)
        dir_hash = cls._crc32(parent.encode("latin-1")) if parent else 0
        file_hash = cls._crc32(stem.encode("latin-1")) if stem else 0
        if ext:
            ext_bytes = ext.encode("ascii")[:4].ljust(4, b"\x00")
            ext_hash = int.from_bytes(ext_bytes, "little")
        else:
            ext_hash = 0
        return (dir_hash, file_hash, ext_hash)
