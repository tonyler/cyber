#!/usr/bin/env python3
"""
Cybernetics Dashboard — Hedera Edition
Futuristic dark glassmorphism dashboard for raid coordination analytics
Protected by Discord OAuth - requires "Loop 🎩" role
"""

import secrets
import uuid
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response, session
from datetime import datetime
from pathlib import Path
import csv
import sys

try:
    import markdown as _markdown_lib
    def _render_markdown(text: str) -> str:
        return _markdown_lib.markdown(text or '', extensions=['fenced_code', 'nl2br', 'tables'])
except ImportError:
    def _render_markdown(text: str) -> str:
        import html
        return '<p>' + html.escape(text or '').replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'


class ReverseProxied:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = (
            environ.get("HTTP_X_SCRIPT_NAME")
            or environ.get("HTTP_X_FORWARDED_PREFIX")
            or ""
        )
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):]
        return self.app(environ, start_response)


_app_dir = Path(__file__).resolve().parent
_project_root = _app_dir.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root / "dashboard3"))  # discord_auth lives here

from config import PROJECT_ROOT, DATABASE_DIR, flask_secret_key, load_env
from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

load_env()

import os as _os
from functools import wraps as _wraps

from discord_auth import (
    get_oauth_url, exchange_code_for_token,
    get_user_info, check_user_has_role, create_session, delete_session,
    get_current_user, get_avatar_url, is_authenticated,
)

# Derive the main dashboard login URL from the registered callback URI.
# e.g. https://tonyler.is-not-a.dev/cyber/callback -> /cyber/login
_callback_uri = _os.environ.get('DISCORD_REDIRECT_URI', '')
_MAIN_LOGIN_URL = _callback_uri.replace('/callback', '/login') if _callback_uri else None


def login_required(f):
    """Require auth — delegate login to the main dashboard (shared cookie, same domain)."""
    @_wraps(f)
    def _wrap(*args, **kwargs):
        if not is_authenticated():
            if _MAIN_LOGIN_URL:
                # Pass ?next= so dashboard3 redirects back here after OAuth
                next_url = request.url
                discord_login_url = _MAIN_LOGIN_URL.replace('/login', '/discord-login')
                return redirect(f"{discord_login_url}?next={next_url}")
            return redirect('/login')
        return f(*args, **kwargs)
    return _wrap

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Simple TTL cache
# ---------------------------------------------------------------------------
_cache: dict = {}

def _cached(key: str, ttl: int, fn):
    now = time.monotonic()
    entry = _cache.get(key)
    if entry and now < entry[1]:
        return entry[0]
    value = fn()
    _cache[key] = (value, now + ttl)
    return value

app = Flask(__name__)
app.config['SECRET_KEY'] = flask_secret_key()
app.wsgi_app = ReverseProxied(app.wsgi_app)
app.jinja_env.filters['markdown'] = _render_markdown


@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'private, no-cache'
    return response

DB_DIR = DATABASE_DIR
MEMBERS_DB = str(DB_DIR / "members.csv")
LINKS_DB = str(DB_DIR / "links.csv")
CALENDAR_DB = str(DB_DIR / "calendar_events.csv")
MONTHLY_VIEWS_DIR = DATABASE_DIR / "monthly_views"
MONTHLY_ACTIONS_DIR = DATABASE_DIR / "monthly_actions"
MONTHLY_VIEWS_DIR.mkdir(parents=True, exist_ok=True)
MONTHLY_ACTIONS_DIR.mkdir(parents=True, exist_ok=True)

CALENDAR_FIELDS = ['id', 'date', 'title', 'instructions', 'preparation_notes', 'created_by', 'created_at']

try:
    members_service = MembersDBService(MEMBERS_DB)
    links_service = LinksDBService(LINKS_DB)
    logger.info("Hedera Dashboard — Services initialized")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    members_service = None
    links_service = None


def _as_int(value) -> int:
    if not value:
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return 0


def _current_month() -> str:
    return datetime.now().strftime('%Y-%m')


def _requested_month(default: str = '') -> str:
    raw = request.args.get('month')
    return default if raw is None else raw.strip()


# ── OAuth ────────────────────────────────────────────────────────────────────

@app.route('/login')
def login():
    if is_authenticated():
        return redirect(url_for('index'))
    # Send user to the main dashboard's login (shared cookie on same domain)
    if _MAIN_LOGIN_URL:
        return redirect(_MAIN_LOGIN_URL)
    return render_template('landing.html', login_url=_MAIN_LOGIN_URL or '#')


@app.route('/discord-login')
def discord_login():
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    return redirect(get_oauth_url(state))


@app.route('/logout')
def logout():
    session_id = request.cookies.get('cyber_session')
    if session_id:
        delete_session(session_id)
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('cyber_session')
    return response


@app.route('/callback')
def oauth_callback():
    from config import discord_token
    if request.args.get('error'):
        return f"<h1>Authentication Failed</h1><p>{request.args.get('error')}</p>", 400
    code = request.args.get('code')
    if request.args.get('state') != session.get('oauth_state'):
        return "<h1>Invalid State</h1>", 400
    token_data = exchange_code_for_token(code)
    if not token_data:
        return "<h1>Authentication Failed</h1>", 400
    access_token = token_data.get('access_token')
    user_info = get_user_info(access_token)
    if not user_info:
        return "<h1>Authentication Failed</h1>", 400
    user_id = user_info.get('id')
    username = user_info.get('username')
    avatar = user_info.get('avatar')
    if not check_user_has_role(user_id, discord_token()):
        return (
            f'<div style="font-family:sans-serif;max-width:600px;margin:100px auto;text-align:center;">'
            f'<h1 style="color:#f472b6;">Access Denied</h1>'
            f'<p>Sorry <strong>{username}</strong>, you need the <strong>"Loop 🎩"</strong> role.</p>'
            f'<a href="{url_for("logout")}" style="padding:10px 20px;background:#6366f1;color:white;'
            f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">Try Again</a>'
            f'</div>'
        ), 403
    session_id = create_session(user_id, username, avatar)
    next_url = session.pop('next_url', url_for('index'))
    response = make_response(redirect(next_url))
    response.set_cookie('cyber_session', session_id, max_age=30 * 24 * 60 * 60, httponly=True, samesite='Lax')
    logger.info(f"User {username} logged in")
    return response


def _get_scraper_status() -> dict:
    return _cached('scraper_status', 30, _read_scraper_status)


def _read_scraper_status() -> dict:
    log_path = PROJECT_ROOT / "logs" / "scrapers.log"
    if not log_path.exists():
        return {'ok': True}
    try:
        size = log_path.stat().st_size
        read_bytes = min(size, 16384)
        with log_path.open('r', encoding='utf-8', errors='replace') as f:
            if size > read_bytes:
                f.seek(size - read_bytes)
                f.readline()
            tail = f.read()
    except Exception:
        return {'ok': True}
    for pattern, message in [
        ('account/access', 'X session cookies expired'),
        ('security verification', 'Cloudflare blocking scraper'),
        ('Enable JavaScript and cookies', 'Cloudflare challenge'),
        ("Executable doesn't exist", 'Playwright browser not installed'),
    ]:
        if pattern in tail:
            return {'ok': False, 'message': message}
    import re
    zero_found = len(re.findall(r'Found 0 tweet elements', tail))
    links_processed = len(re.findall(r'Processing link \d+/\d+', tail))
    if links_processed >= 3 and zero_found >= links_processed:
        return {'ok': False, 'message': 'Scraper finding no data — likely blocked'}
    return {'ok': True}


@app.context_processor
def inject_user():
    user = get_current_user()
    if user:
        user['avatar_url'] = get_avatar_url(user.get('user_id'), user.get('avatar'))
    return {'current_user': user, 'is_authenticated': is_authenticated(), 'scraper_status': _get_scraper_status()}


# ── Data helpers ─────────────────────────────────────────────────────────────

def _load_monthly_views(month_key: str) -> list:
    path = MONTHLY_VIEWS_DIR / f"{month_key}-views.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({"date": row.get("date", ""), "total_views": str(_as_int(row.get("total_views"))), "difference": str(_as_int(row.get("difference")))})
    return sorted(rows, key=lambda r: r.get("date", ""))


def _load_monthly_actions(month_key: str) -> list:
    path = MONTHLY_ACTIONS_DIR / f"{month_key}-actions.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({"date": row.get("date", ""), "total_actions": str(_as_int(row.get("total_actions"))), "difference": str(_as_int(row.get("difference")))})
    return sorted(rows, key=lambda r: r.get("date", ""))


def _build_overview_stats(tasks: list) -> dict:
    return {
        'impressions_total': sum(_as_int(t.get('impressions')) for t in tasks),
        'x_posts': sum(1 for t in tasks if t.get('platform') == 'x' and t.get('task_type') == 'content'),
        'reddit_posts': sum(1 for t in tasks if t.get('platform') == 'reddit' and t.get('task_type') == 'content'),
    }


def _prepare_content_posts(tasks: list) -> tuple:
    content = sorted([t for t in tasks if t.get('task_type') == 'content'],
                     key=lambda t: t.get('date') or '', reverse=True)
    for post in content:
        post["display_title"] = (post.get("title") or post.get("content") or
                                  post.get("description") or post.get("target_url") or "Untitled")
        if post.get("target_url"):
            post["target_url"] = _normalize_embed_url(post["target_url"], post.get("platform", ""))
    return [t for t in content if t.get('platform') == 'x'], [t for t in content if t.get('platform') == 'reddit']


_URL_CACHE_FILE = PROJECT_ROOT / "database" / "url_cache.json"


def _load_url_cache() -> dict:
    try:
        if _URL_CACHE_FILE.exists():
            import json
            return json.loads(_URL_CACHE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_url_cache(cache: dict) -> None:
    try:
        import json
        _URL_CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        logger.warning(f"Could not save URL cache: {e}")


_reddit_url_cache: dict = _load_url_cache()


def _resolve_reddit_short_url(url: str) -> str:
    """Resolve Reddit /s/<id> share links to canonical /r/.../comments/... URLs.

    Reddit blocks all unauthenticated server-side resolution of /s/ URLs.
    Known mappings are stored in database/url_cache.json and can be added manually
    or via the admin interface. Unknown /s/ URLs are returned unchanged (fallback card).
    """
    if url in _reddit_url_cache:
        return _reddit_url_cache[url]
    logger.warning(f"Unresolvable Reddit share URL (not in cache): {url}")
    return url


def _normalize_embed_url(url: str, platform: str = '') -> str:
    """Normalize a post URL to the canonical form required by platform embeds.

    X/Twitter: twitter.com and x.com both work — no change needed.
    Reddit:
      - /s/<id> share links → resolved via HTTP redirect to canonical URL
      - old.reddit.com      → www.reddit.com  (embed widget requires www)
      - UTM params          → stripped (noise for the embed widget)
    """
    if not url:
        return url
    if platform == 'reddit' or 'reddit.com' in url or 'redd.it' in url:
        # Resolve /s/ share links first
        if '/s/' in url:
            url = _resolve_reddit_short_url(url)
        url = url.replace('old.reddit.com', 'www.reddit.com')
        url = url.replace('://reddit.com', '://www.reddit.com')
        # Strip UTM and share params
        from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
        parsed = urlparse(url)
        clean_qs = [(k, v) for k, v in parse_qsl(parsed.query)
                    if not k.startswith('utm_') and k not in ('share_id', 'ref', 'ref_source')]
        url = urlunparse(parsed._replace(query=urlencode(clean_qs)))
    return url


def _is_reddit_embeddable(url: str) -> bool:
    """Return True only for canonical Reddit post URLs the embed widget supports."""
    if not url:
        return False
    from urllib.parse import urlparse
    path = urlparse(url).path
    return '/comments/' in path




def _apply_member_profile_fallbacks(member: dict) -> None:
    x_handle = member.get('x_handle', '')
    if not x_handle or x_handle.lower() in ('active', 'inactive', ''):
        x_profile_url = member.get('x_profile_url', '')
        if x_profile_url:
            if 'x.com/' in x_profile_url or 'twitter.com/' in x_profile_url:
                member['x_handle'] = x_profile_url.rstrip('/').split('/')[-1]
            else:
                member['x_handle'] = x_profile_url.lstrip('@')


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    current_month = _current_month()
    try:
        selected_month = _requested_month(current_month)
        tasks = _cached(f'tasks:{selected_month}', 60, lambda: members_service.get_tasks_for_month(selected_month)) if members_service else []
        stats = _build_overview_stats(tasks)
        x_posts, reddit_posts = _prepare_content_posts(tasks)
        available_months = _cached('task_months', 60, members_service.get_available_task_months) if members_service else []
        views_progress = _cached(f'views:{selected_month}', 60, lambda: _load_monthly_views(selected_month))
        actions_progress = _cached(f'actions:{selected_month}', 60, lambda: _load_monthly_actions(selected_month))
        return render_template('index.html', stats=stats, x_posts=x_posts, reddit_posts=reddit_posts,
                               current_month=current_month, selected_month=selected_month,
                               available_months=available_months, views_progress=views_progress,
                               actions_progress=actions_progress, performance_month=selected_month,
                               performance_scope_label=selected_month or 'All Time',
                               show_performance_charts=bool(selected_month))
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return render_template('index.html', stats={}, x_posts=[], reddit_posts=[], available_months=[],
                               views_progress=[], actions_progress=[], performance_month=current_month,
                               performance_scope_label=current_month, show_performance_charts=True)


@app.route('/members')
@login_required
def members():
    try:
        selected_month = _requested_month('')
        all_members = _cached('all_members', 60, members_service.get_all_members) if members_service else []
        available_months = _cached('activity_months', 60, members_service.get_available_activity_months) if members_service else []
        _empty_stats = {'x_comments': 0, 'x_quotes': 0, 'x_retweets': 0, 'reddit_comments': 0, 'total_contributions': 0}
        all_stats = _cached(f'member_stats:{selected_month}', 60, lambda: members_service.get_all_member_stats(selected_month)) if members_service else {}
        for member in all_members:
            _apply_member_profile_fallbacks(member)
            member.update(all_stats.get((member.get('discord_user') or '').lower(), _empty_stats))
        all_members.sort(key=lambda m: (m.get('total_contributions', 0), m.get('last_active') or '',
                                         (m.get('discord_user') or '').lower()), reverse=True)
        return render_template('members.html', members=all_members, selected_month=selected_month,
                               available_months=available_months, selected_scope_label=selected_month or 'All Time')
    except Exception as e:
        logger.error(f"Error loading members: {e}")
        return render_template('members.html', members=[], selected_month='', available_months=[], selected_scope_label='All Time')


@app.route('/activity')
@login_required
def activity():
    try:
        month = _requested_month(_current_month())
        platform = request.args.get('platform', 'all').strip().lower()
        activities = _cached(f'activity:{month}', 60, lambda: members_service.get_combined_activity_history(month)) if members_service else []
        if platform != 'all':
            activities = [a for a in activities if a.get('platform') == platform]
        return render_template('activity.html', activities=activities, month=month, platform=platform)
    except Exception as e:
        logger.error(f"Error loading activity: {e}")
        return render_template('activity.html', activities=[], month=datetime.now().strftime('%Y-%m'), platform='all')


@app.route('/x')
@login_required
def x_posts_page():
    try:
        selected_month = _requested_month(_current_month())
        tasks = _cached(f'tasks:{selected_month}', 60, lambda: members_service.get_tasks_for_month(selected_month)) if members_service else []
        x_posts, _ = _prepare_content_posts(tasks)
        available_months = _cached('task_months', 60, members_service.get_available_task_months) if members_service else []
        return render_template('x.html', x_posts=x_posts, selected_month=selected_month, available_months=available_months)
    except Exception as e:
        logger.error(f"Error loading X posts: {e}")
        return render_template('x.html', x_posts=[], selected_month='', available_months=[])


@app.route('/reddit')
@login_required
def reddit_posts_page():
    try:
        selected_month = _requested_month(_current_month())
        tasks = _cached(f'tasks:{selected_month}', 60, lambda: members_service.get_tasks_for_month(selected_month)) if members_service else []
        _, reddit_posts = _prepare_content_posts(tasks)
        available_months = _cached('task_months', 60, members_service.get_available_task_months) if members_service else []
        return render_template('reddit.html', reddit_posts=reddit_posts, selected_month=selected_month, available_months=available_months)
    except Exception as e:
        logger.error(f"Error loading Reddit posts: {e}")
        return render_template('reddit.html', reddit_posts=[], selected_month='', available_months=[])


@app.route('/api/stats')
@login_required
def api_stats():
    try:
        selected_month = _requested_month(_current_month())
        tasks = _cached(f'tasks:{selected_month}', 60, lambda: members_service.get_tasks_for_month(selected_month)) if members_service else []
        return jsonify({**_build_overview_stats(tasks), 'month': selected_month})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Calendar ─────────────────────────────────────────────────────────────────

def _is_calendar_editor() -> bool:
    import os
    user = get_current_user()
    if not user:
        return False
    editors_raw = os.environ.get('CALENDAR_EDITORS', '')
    if not editors_raw.strip():
        return False
    editors = [e.strip() for e in editors_raw.split(',') if e.strip()]
    return (user.get('id') or '') in editors


def _load_calendar_events() -> list:
    path = Path(CALENDAR_DB)
    if not path.exists():
        return []
    events = []
    with path.open(newline='', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            events.append(dict(row))
    return sorted(events, key=lambda e: e.get('date', ''), reverse=True)


def _save_calendar_events(events: list) -> None:
    with Path(CALENDAR_DB).open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=CALENDAR_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(events)


def _enrich_events(events: list) -> list:
    return [{**ev, 'preparation_html': _render_markdown(ev.get('preparation_notes', ''))} for ev in events]


@app.route('/calendar')
@login_required
def calendar():
    try:
        events = _enrich_events(_load_calendar_events())
        return render_template('calendar.html', events=events, is_editor=_is_calendar_editor())
    except Exception as e:
        logger.error(f"Error loading calendar: {e}")
        return render_template('calendar.html', events=[], is_editor=False)


@app.route('/calendar/create', methods=['POST'])
@login_required
def calendar_create():
    if not _is_calendar_editor():
        return 'Forbidden', 403
    user = get_current_user()
    events = _load_calendar_events()
    events.append({'id': str(uuid.uuid4()), 'date': request.form.get('date', '').strip(),
                   'title': request.form.get('title', '').strip(), 'instructions': request.form.get('instructions', '').strip(),
                   'preparation_notes': request.form.get('preparation_notes', '').strip(),
                   'created_by': user.get('username', '') if user else '', 'created_at': datetime.now().isoformat()})
    _save_calendar_events(events)
    return redirect(url_for('calendar'))


@app.route('/calendar/edit/<event_id>', methods=['POST'])
@login_required
def calendar_edit(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    events = []
    for ev in _load_calendar_events():
        if ev.get('id') == event_id:
            ev = {**ev, 'date': request.form.get('date', ev.get('date', '')).strip(),
                  'title': request.form.get('title', ev.get('title', '')).strip(),
                  'instructions': request.form.get('instructions', ev.get('instructions', '')).strip(),
                  'preparation_notes': request.form.get('preparation_notes', ev.get('preparation_notes', '')).strip()}
        events.append(ev)
    _save_calendar_events(events)
    return redirect(url_for('calendar'))


@app.route('/calendar/prep/<event_id>', methods=['POST'])
@login_required
def calendar_prep(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    events = [{**ev, 'preparation_notes': request.form.get('preparation_notes', '').strip()}
              if ev.get('id') == event_id else ev for ev in _load_calendar_events()]
    _save_calendar_events(events)
    return redirect(url_for('calendar'))


@app.route('/calendar/delete/<event_id>', methods=['POST'])
@login_required
def calendar_delete(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    _save_calendar_events([ev for ev in _load_calendar_events() if ev.get('id') != event_id])
    return redirect(url_for('calendar'))


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': 'hedera-1.0', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    logger.info("Starting Hedera Dashboard on port 5003")
    app.run(host='0.0.0.0', port=5003, debug=False)
