from typing import Dict, List, Optional, Set
from datetime import datetime
import hashlib
import re
from logger_config import setup_logger

logger = setup_logger(__name__)

class MembersSheetsParser:
    def __init__(self):
        logger.info("MembersSheetsParser initialized")

    def parse_members_registry(self, rows: List[List[str]]) -> List[Dict]:
        logger.info("Parsing Member Registry")
        members = []

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    logger.debug(f"Header row: {row}")
                    continue

                if not row or len(row) == 0:
                    continue

                discord_user = row[0].strip() if len(row) > 0 and row[0] else None
                if not discord_user:
                    continue

                member = {
                    'discord_user': discord_user,
                    'x_handle': self._normalize_x_handle(row[3]) if len(row) > 3 and row[3] else None,
                    'reddit_username': self._normalize_reddit_username(row[4]) if len(row) > 4 and row[4] else None,
                    'status': row[5].strip().lower() if len(row) > 5 and row[5] else 'active',
                    'joined_date': self._parse_date(row[6]) if len(row) > 6 and row[6] else None,
                    'last_activity': self._parse_date(row[7]) if len(row) > 7 and row[7] else None,
                    'total_points': self._parse_int(row[8]) if len(row) > 8 and row[8] else 0
                }

                members.append(member)
                logger.debug(f"Parsed member: {member['discord_user']}")

            logger.info(f"Parsed {len(members)} members from registry")
            return members

        except Exception as e:
            logger.error(f"Error parsing members registry: {str(e)}", exc_info=True)
            return members

    def parse_coordinated_tasks(self, rows: List[List[str]]) -> List[Dict]:
        logger.info("Parsing Coordinated Tasks")
        tasks = []

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    logger.debug(f"Header row: {row}")
                    continue

                if not row or len(row) == 0:
                    continue

                task_id = row[0].strip() if len(row) > 0 and row[0] else None
                if not task_id:
                    continue

                task = {
                    'task_id': task_id,
                    'platform': row[1].strip().lower() if len(row) > 1 and row[1] else None,
                    'action_type': row[2].strip() if len(row) > 2 and row[2] else None,
                    'target_url': row[3].strip() if len(row) > 3 and row[3] else None,
                    'created_date': self._parse_date(row[4]) if len(row) > 4 and row[4] else None,
                    'deadline': self._parse_date(row[5]) if len(row) > 5 and row[5] else None,
                    'description': row[6].strip() if len(row) > 6 and row[6] else None,
                    'participation_count': self._parse_int(row[7]) if len(row) > 7 and row[7] else 0,
                    'is_active': 1
                }

                tasks.append(task)
                logger.debug(f"Parsed task: {task['task_id']}")

            logger.info(f"Parsed {len(tasks)} coordinated tasks")
            return tasks

        except Exception as e:
            logger.error(f"Error parsing coordinated tasks: {str(e)}", exc_info=True)
            return tasks

    def parse_x_activity_log(self, rows: List[List[str]]) -> List[Dict]:
        logger.info("Parsing X Activity Log")
        activities = []

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    logger.debug(f"Header row: {row}")
                    continue

                if not row or len(row) == 0:
                    continue

                discord_user = row[2].strip() if len(row) > 2 and row[2] else None
                target_url = row[6].strip() if len(row) > 6 and row[6] else None

                if not discord_user or not target_url:
                    continue

                activity = {
                    'date': self._parse_date(row[0]) if len(row) > 0 and row[0] else None,
                    'time': self._parse_time(row[1]) if len(row) > 1 and row[1] else None,
                    'discord_user': discord_user,
                    'x_handle': self._normalize_x_handle(row[3]) if len(row) > 3 and row[3] else None,
                    'activity_type': row[4].strip() if len(row) > 4 and row[4] else None,
                    'activity_url': row[5].strip() if len(row) > 5 and row[5] else None,
                    'target_url': target_url,
                    'task_id': row[7].strip() if len(row) > 7 and row[7] else None,
                    'notes': row[8].strip() if len(row) > 8 and row[8] else None
                }

                activities.append(activity)

            logger.info(f"Parsed {len(activities)} X activities")
            return activities

        except Exception as e:
            logger.error(f"Error parsing X activity log: {str(e)}", exc_info=True)
            return activities

    def parse_reddit_activity_log(self, rows: List[List[str]]) -> List[Dict]:
        logger.info("Parsing Reddit Activity Log")
        activities = []

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    logger.debug(f"Header row: {row}")
                    continue

                if not row or len(row) == 0:
                    continue

                discord_user = row[2].strip() if len(row) > 2 and row[2] else None
                target_url = row[6].strip() if len(row) > 6 and row[6] else None

                if not discord_user or not target_url:
                    continue

                activity = {
                    'date': self._parse_date(row[0]) if len(row) > 0 and row[0] else None,
                    'time': self._parse_time(row[1]) if len(row) > 1 and row[1] else None,
                    'discord_user': discord_user,
                    'reddit_username': self._normalize_reddit_username(row[3]) if len(row) > 3 and row[3] else None,
                    'activity_type': row[4].strip() if len(row) > 4 and row[4] else None,
                    'activity_url': row[5].strip() if len(row) > 5 and row[5] else None,
                    'target_url': target_url,
                    'task_id': row[7].strip() if len(row) > 7 and row[7] else None,
                    'upvotes': self._parse_int(row[8]) if len(row) > 8 and row[8] else 0,
                    'comments': self._parse_int(row[9]) if len(row) > 9 and row[9] else 0,
                    'notes': row[10].strip() if len(row) > 10 and row[10] else None
                }

                activities.append(activity)

            logger.info(f"Parsed {len(activities)} Reddit activities")
            return activities

        except Exception as e:
            logger.error(f"Error parsing Reddit activity log: {str(e)}", exc_info=True)
            return activities

    def parse_monthly_content_tasks(self, rows: List[List[str]], year_month: str) -> List[Dict]:
        logger.info("Parsing Monthly Content Tasks")
        tasks: List[Dict] = []

        try:
            header_index = self._find_header_row_index(rows)
            header_row = rows[header_index] if header_index is not None else []
            if header_row:
                logger.info("Content task header row: %s", header_row)
            column_map = self._get_content_column_map(header_row)
            column_map = self._infer_content_columns(rows, column_map)
            logger.info("Content task column map: %s", column_map)
            for i, row in enumerate(rows):
                if header_index is not None and i == header_index:
                    logger.debug(f"Header row: {row}")
                    continue
                if header_index is None and i == 0:
                    logger.debug(f"Header row: {row}")
                    continue

                if not row:
                    continue

                x_task = self._build_content_task(
                    platform="x",
                    date_value=self._row_value(row, column_map["x"]["date"]),
                    author=self._row_value(row, column_map["x"]["author"]),
                    url=self._row_value(row, column_map["x"]["url"]),
                    impressions=self._row_value(row, column_map["x"]["impressions"]),
                    likes=self._row_value(row, column_map["x"]["likes"]),
                    comments=self._row_value(row, column_map["x"]["comments"]),
                    notes=self._row_value(row, column_map["x"]["notes"]),
                    content=self._row_value(row, column_map["x"]["content"]),
                    title=self._row_value(row, column_map["x"]["title"]),
                    year_month=year_month,
                )
                if x_task:
                    tasks.append(x_task)

                reddit_task = self._build_content_task(
                    platform="reddit",
                    date_value=self._row_value(row, column_map["reddit"]["date"]),
                    author=self._row_value(row, column_map["reddit"]["author"]),
                    url=self._row_value(row, column_map["reddit"]["url"]),
                    impressions=self._row_value(row, column_map["reddit"]["impressions"]),
                    likes=self._row_value(row, column_map["reddit"]["likes"]),
                    comments=self._row_value(row, column_map["reddit"]["comments"]),
                    notes=self._row_value(row, column_map["reddit"]["notes"]),
                    content=self._row_value(row, column_map["reddit"]["content"]),
                    title=self._row_value(row, column_map["reddit"]["title"]),
                    year_month=year_month,
                )
                if reddit_task:
                    tasks.append(reddit_task)

            logger.info(f"Parsed {len(tasks)} monthly content tasks")
            return tasks

        except Exception as e:
            logger.error(f"Error parsing monthly content tasks: {str(e)}", exc_info=True)
            return tasks

    def _build_content_task(
        self,
        platform: str,
        date_value: Optional[str],
        author: Optional[str],
        url: Optional[str],
        impressions: Optional[str],
        likes: Optional[str],
        comments: Optional[str],
        notes: Optional[str],
        content: Optional[str],
        title: Optional[str],
        year_month: str,
    ) -> Optional[Dict]:
        if not url:
            return None

        normalized_author = author.strip() if author else None
        if normalized_author and self._is_time_like(normalized_author):
            normalized_author = None
        if not normalized_author:
            normalized_author = self._infer_author_from_url(platform, url)
        if not normalized_author:
            normalized_author = "unknown"

        task_id = self._hash_task_id(platform, url)
        target_url = self._normalize_target_url(platform, url, normalized_author)
        if not target_url:
            return None

        return {
            'task_id': task_id,
            'platform': platform,
            'task_type': 'content',
            'target_url': target_url,
            'description': notes.strip() if notes else None,
            'content': content.strip() if content else None,
            'title': title.strip() if title else None,
            'impressions': self._parse_int(impressions) if impressions else 0,
            'likes': self._parse_int(likes) if likes else 0,
            'comments': self._parse_int(comments) if comments else 0,
            'is_active': 1,
            'created_date': self._parse_date(date_value) if date_value else None,
            'created_by': normalized_author,
            'year_month': year_month,
        }

    def _hash_task_id(self, platform: str, url: str) -> str:
        digest = hashlib.sha1(f"{platform}:{url}".encode("utf-8")).hexdigest()
        return digest[:50]

    def _infer_author_from_url(self, platform: str, url: str) -> Optional[str]:
        try:
            if platform == "x":
                parts = url.split("/")
                if len(parts) > 3:
                    candidate = parts[3].strip().lower()
                    if candidate and candidate not in {"i", "status"}:
                        return candidate.lstrip("@")
                return None

            if platform == "reddit":
                if "/user/" in url:
                    return url.split("/user/", 1)[1].split("/", 1)[0].strip().lower()
                if "/u/" in url:
                    return url.split("/u/", 1)[1].split("/", 1)[0].strip().lower()
        except Exception:
            return None

        return None

    def _is_time_like(self, value: str) -> bool:
        if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", value):
            return True
        return False

    def _normalize_target_url(self, platform: str, url: str, author: Optional[str]) -> Optional[str]:
        if not url:
            return None

        candidate = url.strip()
        if platform == "x":
            status_id = self._extract_x_status_id(candidate)
            if status_id:
                return f"https://x.com/i/status/{status_id}"
            return None

        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate

        return None

    def _extract_x_status_id(self, url: str) -> Optional[str]:
        if not url:
            return None
        if url.isdigit():
            return url
        match = re.search(r"/status(?:es)?/(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _row_value(self, row: List[str], index: Optional[int]) -> Optional[str]:
        if index is None or index < 0:
            return None
        if index >= len(row):
            return None
        value = row[index]
        if value is None:
            return None
        value = value.strip()
        return value or None

    def _find_header_row_index(self, rows: List[List[str]]) -> Optional[int]:
        if not rows:
            return None

        def normalize_label(value: str) -> str:
            value = (value or "").strip().lower()
            value = value.replace("_", " ").replace("-", " ")
            return " ".join(value.split())

        for idx, row in enumerate(rows[:3]):
            labels = {normalize_label(cell) for cell in row if cell and cell.strip()}
            if "date" in labels and "url" in labels:
                return idx

        return 0

    def _get_content_column_map(self, header: List[str]) -> Dict[str, Dict[str, Optional[int]]]:
        defaults = {
            "x": {
                "date": 0,
                "author": 1,
                "url": 2,
                "impressions": 3,
                "likes": 4,
                "comments": 5,
                "notes": 6,
                "content": None,
                "title": None,
            },
            "reddit": {
                "date": 8,
                "author": 9,
                "url": 10,
                "impressions": 11,
                "likes": 12,
                "comments": 13,
                "notes": 14,
                "content": None,
                "title": None,
            },
        }

        if not header:
            return defaults

        def normalize_label(value: str) -> str:
            value = (value or "").strip().lower()
            value = value.replace("_", " ").replace("-", " ")
            return " ".join(value.split())

        labels = [normalize_label(cell) for cell in header]

        def indices_for(names: Set[str]) -> List[int]:
            return [i for i, label in enumerate(labels) if label in names]

        def pick(indices: List[int], occurrence: int, fallback: Optional[int]) -> Optional[int]:
            if len(indices) > occurrence:
                return indices[occurrence]
            return fallback

        date_idx = indices_for({"date"})
        author_idx = indices_for({"author"})
        url_idx = indices_for({"url"})
        impressions_idx = indices_for({"impressions"})
        views_idx = indices_for({"views"})
        likes_idx = indices_for({"likes"})
        upvotes_idx = indices_for({"upvotes"})
        comments_idx = indices_for({"comments"})
        notes_idx = indices_for({"notes"})
        content_idx = indices_for({"content", "post content", "content text", "post text", "text", "body", "caption"})
        title_idx = indices_for({"title", "post title", "headline", "subject"})

        x_content_idx = indices_for({"x content", "x post content", "tweet content", "tweet text", "x text"})
        reddit_content_idx = indices_for({"reddit content", "reddit post content", "reddit text"})
        x_title_idx = indices_for({"x title", "x post title", "tweet title"})
        reddit_title_idx = indices_for({"reddit title", "reddit post title"})

        column_map = {
            "x": {
                "date": pick(date_idx, 0, defaults["x"]["date"]),
                "author": pick(author_idx, 0, defaults["x"]["author"]),
                "url": pick(url_idx, 0, defaults["x"]["url"]),
                "impressions": pick(impressions_idx, 0, defaults["x"]["impressions"]),
                "likes": pick(likes_idx, 0, defaults["x"]["likes"]),
                "comments": pick(comments_idx, 0, defaults["x"]["comments"]),
                "notes": pick(notes_idx, 0, defaults["x"]["notes"]),
                "content": pick(x_content_idx, 0, pick(content_idx, 0, defaults["x"]["content"])),
                "title": pick(x_title_idx, 0, pick(title_idx, 0, defaults["x"]["title"])),
            },
            "reddit": {
                "date": pick(date_idx, 1, defaults["reddit"]["date"]),
                "author": pick(author_idx, 1, defaults["reddit"]["author"]),
                "url": pick(url_idx, 1, defaults["reddit"]["url"]),
                "impressions": pick(impressions_idx, 1, defaults["reddit"]["impressions"]),
                "likes": pick(upvotes_idx, 0, defaults["reddit"]["likes"]),
                "comments": pick(comments_idx, 1, defaults["reddit"]["comments"]),
                "notes": pick(notes_idx, 1, defaults["reddit"]["notes"]),
                "content": pick(reddit_content_idx, 0, pick(content_idx, 1, defaults["reddit"]["content"])),
                "title": pick(reddit_title_idx, 0, pick(title_idx, 1, defaults["reddit"]["title"])),
            },
        }

        if column_map["reddit"]["impressions"] == defaults["reddit"]["impressions"] and views_idx:
            column_map["reddit"]["impressions"] = pick(views_idx, 0, defaults["reddit"]["impressions"])

        return column_map

    def _infer_content_columns(
        self,
        rows: List[List[str]],
        column_map: Dict[str, Dict[str, Optional[int]]],
    ) -> Dict[str, Dict[str, Optional[int]]]:
        def is_numeric(value: str) -> bool:
            return bool(re.fullmatch(r"[\d,.\-]+", value))

        def candidate_columns(
            start: int,
            end: int,
            exclude: set[int],
        ) -> List[int]:
            stats: Dict[int, List[int]] = {}
            for row in rows[:50]:
                if end > 0 and len(row) <= start:
                    continue
                stop = min(end, len(row)) if end > 0 else len(row)
                for idx in range(start, stop):
                    if idx in exclude:
                        continue
                    value = row[idx] if idx < len(row) else ""
                    value = value.strip() if value else ""
                    if not value or "http://" in value or "https://" in value:
                        continue
                    if is_numeric(value):
                        continue
                    total, count = stats.get(idx, [0, 0])
                    total += len(value)
                    count += 1
                    stats[idx] = [total, count]
            ranked = sorted(
                stats.items(),
                key=lambda item: (item[1][0] / max(1, item[1][1])),
                reverse=True,
            )
            return [idx for idx, _ in ranked]

        x_url_idx = column_map["x"].get("url")
        reddit_url_idx = column_map["reddit"].get("url")
        x_notes_idx = column_map["x"].get("notes") or 0
        reddit_notes_idx = column_map["reddit"].get("notes") or 0

        x_start = x_notes_idx + 1
        x_end = reddit_url_idx if isinstance(reddit_url_idx, int) else 0
        reddit_start = reddit_notes_idx + 1
        reddit_end = 0

        x_exclude = {idx for idx in column_map["x"].values() if isinstance(idx, int)}
        reddit_exclude = {idx for idx in column_map["reddit"].values() if isinstance(idx, int)}

        if column_map["x"].get("content") is None or column_map["x"].get("title") is None:
            x_candidates = candidate_columns(x_start, x_end, x_exclude)
            if column_map["x"].get("content") is None and x_candidates:
                column_map["x"]["content"] = x_candidates[0]
            if column_map["x"].get("title") is None and len(x_candidates) > 1:
                column_map["x"]["title"] = x_candidates[1]

        if column_map["reddit"].get("content") is None or column_map["reddit"].get("title") is None:
            reddit_candidates = candidate_columns(reddit_start, reddit_end, reddit_exclude)
            if column_map["reddit"].get("content") is None and reddit_candidates:
                column_map["reddit"]["content"] = reddit_candidates[0]
            if column_map["reddit"].get("title") is None and len(reddit_candidates) > 1:
                column_map["reddit"]["title"] = reddit_candidates[1]

        return column_map
    def _normalize_x_handle(self, handle: str) -> Optional[str]:
        if not handle:
            return None

        normalized = handle.strip().lstrip('@').lower()
        return normalized if normalized else None

    def _normalize_reddit_username(self, username: str) -> Optional[str]:
        if not username:
            return None

        normalized = username.strip().lower()
        if normalized.startswith('u/'):
            normalized = normalized[2:]

        return normalized if normalized else None

    def _parse_int(self, value: str) -> int:
        if not value:
            return 0

        try:
            clean = value.strip().replace(',', '')
            return int(clean)
        except (ValueError, AttributeError):
            logger.debug(f"Could not parse int from: {value}")
            return 0

    def _parse_time(self, value: str) -> Optional[str]:
        if not value or not value.strip():
            return None

        value = value.strip()
        for fmt in ['%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p']:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime('%H:%M:%S')
            except ValueError:
                continue

        return value

    def _parse_datetime(self, value: str) -> Optional[str]:
        if not value or not value.strip():
            return None

        value = value.strip()
        for fmt in [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
        ]:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue

        date_only = self._parse_date(value)
        return f"{date_only} 00:00:00" if date_only else None

    def _parse_date(self, value: str) -> Optional[str]:
        if not value or not value.strip():
            return None

        value = value.strip()

        try:
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%m-%d-%Y']:
                try:
                    parsed = datetime.strptime(value, fmt)
                    return parsed.strftime('%Y-%m-%d')
                except ValueError:
                    continue

            logger.debug(f"Could not parse date: {value}")
            return None

        except Exception as e:
            logger.debug(f"Error parsing date '{value}': {str(e)}")
            return None
