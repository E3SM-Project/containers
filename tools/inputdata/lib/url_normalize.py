from __future__ import annotations

from pathlib import Path
from typing import Optional

PUBLIC_INPUTDATA_PREFIX = "https://web.lcrc.anl.gov/public/e3sm/inputdata"


def filter_candidate_path(value: str) -> bool:
    """Return True when a path candidate looks like model inputdata."""
    token = value.strip().strip('"').strip("'")
    if not token:
        return False

    lowered = token.lower()
    if lowered in {"unset", "none", "null", "na", "n/a"}:
        return False

    blocked_fragments = (
        "baseline",
        "rest",
        "restart",
        "history",
        "output",
        "archive",
    )
    if any(fragment in lowered for fragment in blocked_fragments):
        return False

    if token.endswith("/"):
        return False

    # Inputdata files are file-like paths and almost always include separators.
    if "/" not in token and "\\" not in token:
        return False

    return True


def normalize_to_din_relative(path_value: str, din_loc_root: Path) -> Optional[str]:
    """Normalize path-like text to a DIN_LOC_ROOT-relative unix-style path."""
    value = path_value.strip().strip('"').strip("'")
    value = value.replace("\\", "/")
    if value.startswith("$DIN_LOC_ROOT/"):
        rel = value[len("$DIN_LOC_ROOT/") :]
        return rel.strip("/")

    if value.startswith("${DIN_LOC_ROOT}/"):
        rel = value[len("${DIN_LOC_ROOT}/") :]
        return rel.strip("/")

    din_root_posix = din_loc_root.as_posix().rstrip("/") + "/"
    if value.startswith(din_root_posix):
        rel = value[len(din_root_posix) :]
        return rel.strip("/")

    # Allow already-relative references such as atm/cam/inic/file.nc.
    if not value.startswith("/"):
        return value.strip("/")

    return None


def to_public_inputdata_url(relative_path: str) -> str:
    rel = relative_path.strip().lstrip("/")
    return f"{PUBLIC_INPUTDATA_PREFIX}/{rel}"


def is_public_inputdata_url(url: str) -> bool:
    return url.startswith(PUBLIC_INPUTDATA_PREFIX + "/")
