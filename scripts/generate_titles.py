#!/usr/bin/env python3
"""
Generate short titles for content tasks using Groq and store them in the CSV.
This runs out-of-band so the dashboard stays fast and read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
import sys
import urllib.request


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _generate_short_title_openai(content: str, max_words: int, model: str, api_key: str) -> str:
    content = content.strip()
    if not content:
        return ""

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 64,
        "messages": [
            {
                "role": "system",
                "content": "You write short, factual titles. Output only the title text.",
            },
            {
                "role": "user",
                "content": f"Create a title of up to {max_words} words for this post content:\n{content}",
            },
        ],
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    title = (message.get("content") or "").strip()
    return " ".join(title.split())


def _generate_short_title_groq(content: str, max_words: int, model: str, api_key: str) -> str:
    content = content.strip()
    if not content:
        return ""

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 64,
        "messages": [
            {
                "role": "system",
                "content": "You write short, factual titles. Output only the title text.",
            },
            {
                "role": "user",
                "content": f"Create a title of up to {max_words} words for this post content:\n{content}",
            },
        ],
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    title = (message.get("content") or "").strip()
    return " ".join(title.split())


def _iter_missing_titles(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    pending = []
    for row in rows:
        if row.get("task_type") != "content":
            continue
        if row.get("title"):
            continue
        content = (row.get("content") or "").strip()
        if not content:
            continue
        pending.append(row)
    return pending


def generate_missing_titles(
    csv_path: Path,
    limit: Optional[int] = None,
    sleep_seconds: float = 0.0,
    env_paths: Optional[List[Path]] = None,
) -> int:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "dashboard"))
    from csv_store import locked_csv, merge_fieldnames

    resolved_env_paths = env_paths or [
        project_root / ".env",
        project_root / "dashboard2" / ".env",
    ]
    for env_path in resolved_env_paths:
        _load_env_file(env_path)

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not openai_key and not groq_key:
        return 0

    if openai_key:
        provider = "openai"
        api_key = openai_key
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    else:
        provider = "groq"
        api_key = groq_key
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

    max_words_raw = os.getenv("GROQ_TITLE_MAX_WORDS", "8").strip()
    max_per_request_raw = os.getenv("GROQ_TITLE_MAX_PER_REQUEST", "6").strip()

    try:
        max_words = max(1, min(12, int(max_words_raw)))
    except ValueError:
        max_words = 8

    try:
        max_per_request = max(1, int(max_per_request_raw))
    except ValueError:
        max_per_request = 6

    effective_limit = limit if limit is not None else max_per_request

    with locked_csv(str(csv_path)) as (fields, rows, write):
        fields = merge_fieldnames(fields, ["content", "title"])
        pending = _iter_missing_titles(rows)
        if not pending:
            return 0

        updated = 0
        last_error: Optional[Exception] = None
        for row in pending:
            if updated >= effective_limit:
                break
            content = (row.get("content") or "").strip()
            if not content:
                continue
            content = content[:2000]
            try:
                if provider == "openai":
                    title = _generate_short_title_openai(content, max_words, model, api_key)
                else:
                    title = _generate_short_title_groq(content, max_words, model, api_key)
            except Exception as exc:
                last_error = exc
                continue

            if title:
                row["title"] = title
                updated += 1
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

        if updated:
            write(fields, rows)
        elif last_error:
            raise RuntimeError(f"Title generation failed: {last_error}")

        return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=None, help="Path to coordinated_tasks.csv")
    parser.add_argument("--limit", type=int, default=None, help="Max titles to generate this run")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between requests")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    default_csv = project_root / "database" / "coordinated_tasks.csv"
    csv_path = Path(args.csv) if args.csv else default_csv

    env_paths = [
        project_root / ".env",
        project_root / "dashboard2" / ".env",
    ]
    for env_path in env_paths:
        _load_env_file(env_path)

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not openai_key and not groq_key:
        raise SystemExit("Missing OPENAI_API_KEY or GROQ_API_KEY in .env")

    start = time.time()
    try:
        updated = generate_missing_titles(
            csv_path=csv_path,
            limit=args.limit,
            sleep_seconds=args.sleep,
            env_paths=env_paths,
        )
    except Exception as exc:
        print(f"Title generation error: {exc}")
        return
    duration = time.time() - start
    if updated:
        print(f"Updated {updated} titles in {duration:.2f}s")
    else:
        print("No missing titles found.")


if __name__ == "__main__":
    main()
