import csv
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Tuple
try:
    import fcntl
except Exception:  # pragma: no cover - fallback for non-POSIX
    fcntl = None


def load_csv(path: str, use_lock: bool = True) -> Tuple[List[str], List[Dict[str, str]]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return [], []

    lock_file = None
    try:
        if use_lock:
            lock_path = csv_path.with_suffix(csv_path.suffix + ".lock")
            lock_file = lock_path.open("w")
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_SH)

        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return [], []
            rows = []
            for row in reader:
                rows.append({key: value for key, value in row.items()})
            return list(reader.fieldnames), rows
    finally:
        if lock_file:
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()


def merge_fieldnames(existing: Iterable[str], new_keys: Iterable[str]) -> List[str]:
    fieldnames = list(existing) if existing else []
    for key in new_keys:
        if key not in fieldnames:
            fieldnames.append(key)
    return fieldnames


def write_csv(
    path: str,
    fieldnames: List[str],
    rows: List[Dict[str, str]],
    use_lock: bool = True,
) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    lock_path = csv_path.with_suffix(csv_path.suffix + ".lock")

    lock_file = None
    try:
        if use_lock:
            lock_file = lock_path.open("w")
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
        with tmp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                cleaned = {
                    field: "" if row.get(field) is None else row.get(field)
                    for field in fieldnames
                }
                writer.writerow(cleaned)

        tmp_path.replace(csv_path)
    finally:
        if lock_file:
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()


@contextmanager
def locked_csv(path: str) -> Tuple[List[str], List[Dict[str, str]], Callable]:
    csv_path = Path(path)
    lock_path = csv_path.with_suffix(csv_path.suffix + ".lock")
    lock_file = lock_path.open("w")
    if fcntl:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
    try:
        fields, rows = load_csv(path, use_lock=False)

        def _write(fieldnames: List[str], new_rows: List[Dict[str, str]]) -> None:
            write_csv(path, fieldnames, new_rows, use_lock=False)

        yield fields, rows, _write
    finally:
        if fcntl:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
