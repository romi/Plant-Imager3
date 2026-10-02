import json
import os
import pathlib
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from plantimager.commons.logging import create_logger

TIMELAPSE_STORAGE_JSON = "timelapse_storage.json"

logger = create_logger(__name__)

def get_storage_dir() -> pathlib.Path:
    """Return the path to the storage directory at ``~/.local/share/plant-imager3-app``"""
    return pathlib.Path(os.getenv("XDG_DATA_HOME", pathlib.Path.home() / ".local" / "share")) / "plant-imager3-app"

# ----------------------------------------------------------------------
# Helper functions – JSON‑serialisation of non‑primitive types
# ----------------------------------------------------------------------
def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s is not None else None


def _enum_to_str(e: Optional[StrEnum]) -> Optional[str]:
    return e.value if e is not None else None


def _str_to_enum(cls: Any, s: Optional[str]) -> Optional[StrEnum]:
    return cls(s) if s is not None else None


# ----------------------------------------------------------------------
# Minimal representation of a finished Scan
# ----------------------------------------------------------------------
@dataclass
class ScanRecord:
    """Only the data needed to resume/re‑run a timelapse."""
    scan_id: str
    started_at: Optional[str] = None   # ISO‑8601
    finished_at: Optional[str] = None  # ISO‑8601
    status: str = "pending"             # "succeeded", "failed", "skipped", …
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_scan(cls, scan_obj: Any) -> "ScanRecord":
        """Create a record from a live `Scan` instance."""
        # The real Scan class already stores timestamps as floats;
        # we convert them to ISO strings for readability.
        return cls(
            scan_id=scan_obj.scan_id,
            started_at=_dt_to_iso(
                datetime.fromtimestamp(scan_obj._start_time) if getattr(scan_obj, "_start_time", None) else None
            ),
            finished_at=_dt_to_iso(
                datetime.fromtimestamp(scan_obj._stop_time) if getattr(scan_obj, "_stop_time", None) else None
            ),
            status=getattr(scan_obj, "status", "pending"),
            error=getattr(scan_obj, "error", None),
        )


# ----------------------------------------------------------------------
# The JSON‑backed store
# ----------------------------------------------------------------------
@dataclass
class TimelapseStore:
    """Encapsulates atomic persistence of a TimeLapse object."""
    _file_name: str = os.getenv("PI3_TIMELAPSE_FILE_NAME", TIMELAPSE_STORAGE_JSON)
    version: int = 1

    # The fields below are written to / read from JSON
    timelapse_id: str = ""
    mode: str = ""
    state: str = ""
    schedule_times: List[str] = field(default_factory=list)      # ISO strings
    next_idx: int = 0
    current_idx: int = 0
    warmup_sec: int = 0
    standby_threshold_sec: int = 0
    grace_period: int = 0
    start_at: Optional[str] = None
    scans: List[Dict[str, Any]] = field(default_factory=list)   # list of ScanRecord dicts
    extra: Dict[str, Any] = field(default_factory=dict)        # any additional blob the caller wants to keep

    # ------------------------------------------------------------------
    # Path handling
    # ------------------------------------------------------------------
    @property
    def _full_path(self) -> pathlib.Path:
        return get_storage_dir() / self._file_name

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def _as_serialisable_dict(self) -> Dict[str, Any]:
        """Return a plain‑dict ready for json.dump()."""
        data = {}
        for key, value in asdict(self).items():
            if not key.startswith("_"):  # remove private attributes
                data[key] = value
        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Write the current state to disk atomically."""
        try:
            get_storage_dir().mkdir(parents=True, exist_ok=True)

            # Write to a temporary file in the same directory (rename is atomic on POSIX)
            fd, tmp_path = tempfile.mkstemp(dir=get_storage_dir(), prefix=self._file_name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(self._as_serialisable_dict(), tmp_file, indent=2, sort_keys=True)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            # Replace the old file
            tmp_path_obj = pathlib.Path(tmp_path)
            tmp_path_obj.replace(self._full_path)
            logger.debug(f"Timelapse state saved to {self._full_path}")
        except Exception as exc:
            logger.error(f"Failed to save timelapse state: {exc}")
            raise

    @classmethod
    def new_store_from_last(cls) -> Optional["TimelapseStore"]:
        """
        Load a `TimelapseStore` instance from a stored JSON file in the storage directory.

        This method attempts to recreate a `TimelapseStore` object from a persisted state
        stored in a JSON file. If the JSON file cannot be found or is invalid, the method
        logs the issue and returns `None`. In case of a version mismatch between the stored
        data and the current implementation, the method attempts a best-effort loading process.

        Returns
        -------
        Optional[TimelapseStore]
            A `TimelapseStore` instance reconstructed from the JSON file if successful;
            otherwise, `None`.

        Notes
        -----
        - The JSON file' is located at ``~/.local/share/plant-imager3-app/$PI3_TIMELAPSE_FILE_NAME``.
        If the environment variable is not set, it defaults to `"timelapse_storage.json"`.
        - A basic version check is performed to ensure backward compatibility. If a version
          mismatch is detected, a warning is logged, and the loading process continues on a
          best-effort basis.
        - Any exception encountered during file reading or JSON parsing will be caught, and
          a corresponding error message will be logged.
        """
        store_path = get_storage_dir() / os.getenv(
            "PI3_TIMELAPSE_FILE_NAME", TIMELAPSE_STORAGE_JSON
        )
        if not store_path.is_file():
            logger.info("No persisted timelapse file found – starting fresh.")
            return None

        try:
            with store_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)

            # Basic version check – allow future‑compatible extensions
            if raw.get("version", 1) != cls().version:
                logger.warning("Timelapse file version mismatch; attempting best‑effort load.")

            # Build the object
            obj = cls(
                timelapse_id=raw.get("timelapse_id", ""),
                mode=raw.get("mode", ""),
                state=raw.get("state", ""),
                schedule_times=raw.get("schedule_times", []),
                next_idx=raw.get("next_idx", 0),
                current_idx=raw.get("current_idx", 0),
                warmup_sec=raw.get("warmup_sec", 0),
                standby_threshold_sec=raw.get("standby_threshold_sec", 0),
                grace_period=raw.get("grace_period", 0),
                start_at=raw.get("start_at"),
                scans=raw.get("scans", []),
                extra=raw.get("extra", {}),
                version=raw.get("version", 1),
            )
            logger.debug(f"Timelapse state loaded from {store_path}")
            return obj
        except Exception as exc:
            logger.error(f"Failed to read timelapse state: {exc}")
            return None

    # ------------------------------------------------------------------
    # Convenience helpers for the TimeLapse class
    # ------------------------------------------------------------------
    def to_timelapse_kwargs(self) -> Dict[str, Any]:
        """
        Convert the stored JSON into a dict that can be fed to a new
        `TimeLapse` instance for a quick “resume” path.
        """
        # Convert ISO strings back to datetime objects where required.
        schedule = [_iso_to_dt(s) for s in self.schedule_times]
        start = _iso_to_dt(self.start_at)

        return {
            "timelapse_id": self.timelapse_id,
            "mode": self.mode,
            "state": self.state,
            "schedule_times": schedule,
            "next_idx": self.next_idx,
            "current_idx": self.current_idx,
            "warmup_sec": self.warmup_sec,
            "standby_threshold_sec": self.standby_threshold_sec,
            "grace_period": self.grace_period,
            "start_at": start,
            "scans": [ScanRecord(**s) for s in self.scans],
            "extra": self.extra,
        }

    @staticmethod
    def from_timelapse(tl_obj: Any) -> "TimelapseStore":
        """
        Create a store instance from a *live* TimeLapse object.
        Only the fields that are required for a restart are persisted.
        """
        # Serialize schedule_times as ISO strings
        schedule_iso = [_dt_to_iso(dt) for dt in tl_obj.schedule_times]

        # Build thin ScanRecord objects – we avoid persisting the whole Scan
        # to keep the JSON small and independent of heavy objects.
        scan_records = [asdict(ScanRecord.from_scan(s)) for s in getattr(tl_obj, "scans", [])]

        return TimelapseStore(
            timelapse_id=tl_obj.id,
            mode=_enum_to_str(tl_obj.mode),
            state=_enum_to_str(tl_obj._state),
            schedule_times=schedule_iso,
            next_idx=tl_obj.next_idx,
            current_idx=tl_obj.current_idx,
            warmup_sec=tl_obj.warmup_sec,
            standby_threshold_sec=tl_obj.standby_threshold_sec,
            grace_period=tl_obj.grace_period,
            start_at=_dt_to_iso(tl_obj.start_at),
            scans=scan_records,
            extra={},
        )
