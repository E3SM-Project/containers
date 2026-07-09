from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.inputdata.lib.url_normalize import normalize_to_din_relative, to_public_inputdata_url

CESM_INPUTDATA_PREFIX = "https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata"


@dataclass(frozen=True)
class InputDataValidationResult:
    relative_path: str
    checked_urls: tuple[str, str]
    resolved_url: Optional[str]
    status: str
    message: str = ""


@dataclass(frozen=True)
class UrlProbeResult:
    exists: bool
    verified: bool
    message: str = ""


def _probe_url(url: str) -> UrlProbeResult:
    request = Request(
        url,
        method="HEAD",
        headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
    )
    context = ssl._create_unverified_context()
    try:
        with urlopen(request, timeout=20, context=context) as response:
            status = getattr(response, "status", 200)
            if 200 <= status < 400:
                return UrlProbeResult(exists=True, verified=True)
            return UrlProbeResult(exists=False, verified=False, message=f"unexpected status {status}")
    except HTTPError as exc:
        if exc.code in {404, 410}:
            return UrlProbeResult(exists=False, verified=True, message=f"http {exc.code}")
        return UrlProbeResult(exists=False, verified=False, message=f"http {exc.code}")
    except (URLError, OSError, TimeoutError) as exc:
        return UrlProbeResult(exists=False, verified=False, message=str(exc))


def validate_inputdata_reference(path_value: str, din_loc_root) -> Optional[InputDataValidationResult]:
    relative_path = normalize_to_din_relative(path_value, din_loc_root)
    if not relative_path:
        return None

    e3sm_url = to_public_inputdata_url(relative_path)
    cesm_url = f"{CESM_INPUTDATA_PREFIX}/{relative_path.strip().lstrip('/')}"

    e3sm_probe = _probe_url(e3sm_url)
    if e3sm_probe.exists:
        return InputDataValidationResult(
            relative_path=relative_path,
            checked_urls=(e3sm_url, cesm_url),
            resolved_url=e3sm_url,
            status="e3sm",
        )

    cesm_probe = _probe_url(cesm_url)
    if cesm_probe.exists:
        return InputDataValidationResult(
            relative_path=relative_path,
            checked_urls=(e3sm_url, cesm_url),
            resolved_url=cesm_url,
            status="cesm",
        )

    if e3sm_probe.verified and cesm_probe.verified:
        return InputDataValidationResult(
            relative_path=relative_path,
            checked_urls=(e3sm_url, cesm_url),
            resolved_url=None,
            status="missing",
            message="not found on E3SM or CESM",
        )

    message_parts = []
    if e3sm_probe.message:
        message_parts.append(f"e3sm: {e3sm_probe.message}")
    if cesm_probe.message:
        message_parts.append(f"cesm: {cesm_probe.message}")
    message = "; ".join(message_parts) if message_parts else "validation unavailable"

    return InputDataValidationResult(
        relative_path=relative_path,
        checked_urls=(e3sm_url, cesm_url),
        resolved_url=e3sm_url,
        status="unverified",
        message=message,
    )
