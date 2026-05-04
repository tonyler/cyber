#!/usr/bin/env python3
"""
Cybernetics Dashboard 3.0 - Signal Studio Edition
Clean, bold Flask web application for raid coordination analytics
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
        return _markdown_lib.markdown(
            text or '',
            extensions=['fenced_code', 'nl2br', 'tables']
        )
except ImportError:
    def _render_markdown(text: str) -> str:
        """Fallback: basic html escaping + line breaks."""
        import html
        return '<p>' + html.escape(text or '').replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'


class ReverseProxied:
    """Middleware to handle reverse proxy with subpath (e.g., /cyber)."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Check both X-Script-Name and X-Forwarded-Prefix headers
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


# Add project paths
_app_dir = Path(__file__).resolve().parent
_project_root = _app_dir.parent
sys.path.insert(0, str(_project_root / "shared"))

from config import PROJECT_ROOT, DATABASE_DIR, flask_secret_key, load_env
from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

load_env()

# Import Discord auth after load_env
from discord_auth import (
    login_required,
    get_oauth_url,
    exchange_code_for_token,
    get_user_info,
    check_user_has_role,
    create_session,
    delete_session,
    get_current_user,
    get_avatar_url,
    is_authenticated,
)

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Simple TTL cache — avoids re-reading CSV files on every request
# ---------------------------------------------------------------------------
_cache: dict = {}

def _cached(key: str, ttl: int, fn):
    """Return cached value if fresh, otherwise call fn(), cache and return result."""
    now = time.monotonic()
    entry = _cache.get(key)
    if entry and now < entry[1]:
        return entry[0]
    value = fn()
    _cache[key] = (value, now + ttl)
    return value

def _cache_invalidate(prefix: str = '') -> None:
    """Remove all cache keys that start with prefix (or everything if prefix is empty)."""
    keys = [k for k in list(_cache) if k.startswith(prefix)] if prefix else list(_cache)
    for k in keys:
        _cache.pop(k, None)

app = Flask(__name__)
app.config['SECRET_KEY'] = flask_secret_key()
app.wsgi_app = ReverseProxied(app.wsgi_app)


@app.after_request
def add_cache_headers(response):
    """Set cache headers: long TTL for versioned static assets, no-store for HTML."""
    if request.path.startswith('/static/'):
        # Static assets are fingerprinted by Flask (URL includes filename) — cache 1 year
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif response.content_type and 'text/html' in response.content_type:
        # HTML pages must not be cached by shared caches (auth-gated)
        response.headers['Cache-Control'] = 'private, no-cache'
    return response


# Jinja2 markdown filter
app.jinja_env.filters['markdown'] = _render_markdown

# Database paths
DB_DIR = DATABASE_DIR
MEMBERS_DB = str(DB_DIR / "members.csv")
LINKS_DB = str(DB_DIR / "links.csv")
CALENDAR_DB = str(DB_DIR / "calendar_events.csv")
MONTHLY_VIEWS_DIR = DATABASE_DIR / "monthly_views"
MONTHLY_ACTIONS_DIR = DATABASE_DIR / "monthly_actions"
MONTHLY_VIEWS_DIR.mkdir(parents=True, exist_ok=True)
MONTHLY_ACTIONS_DIR.mkdir(parents=True, exist_ok=True)

CALENDAR_FIELDS = ['id', 'date', 'title', 'instructions', 'preparation_notes', 'created_by', 'created_at']

# Initialize services
try:
    members_service = MembersDBService(MEMBERS_DB)
    links_service = LinksDBService(LINKS_DB)
    logger.info("Dashboard 3.0 - Services initialized")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    members_service = None
    links_service = None


def _as_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        cleaned = str(value).replace(",", "").strip()
        return int(float(cleaned))
    except ValueError:
        return 0


def _current_month() -> str:
    return datetime.now().strftime('%Y-%m')


def _requested_month(default: str = '') -> str:
    raw = request.args.get('month')
    if raw is None:
        return default
    return raw.strip()


# =============================================================================
# Discord OAuth Routes
# =============================================================================


@app.route('/login')
def login():
    """Show landing page with login button."""
    if is_authenticated():
        return redirect(url_for('index'))
    return render_template('landing.html')


@app.route('/discord-login')
def discord_login():
    """Redirect to Discord OAuth."""
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    # Allow cross-dashboard ?next= redirect after login
    next_param = request.args.get('next')
    if next_param:
        session['next_url'] = next_param
    oauth_url = get_oauth_url(state)
    return redirect(oauth_url)


@app.route('/logout')
def logout():
    """Log out and clear session."""
    session_id = request.cookies.get('cyber_session')
    if session_id:
        delete_session(session_id)
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('cyber_session')
    return response


@app.route('/callback')
def oauth_callback():
    """Handle Discord OAuth callback."""
    from config import discord_token

    error = request.args.get('error')
    if error:
        logger.error(f"OAuth error: {error}")
        return f"<h1>Authentication Failed</h1><p>Error: {error}</p>", 400

    code = request.args.get('code')
    state = request.args.get('state')

    # Verify state
    if state != session.get('oauth_state'):
        logger.warning("OAuth state mismatch")
        return "<h1>Invalid State</h1><p>Please try logging in again.</p>", 400

    # Exchange code for token
    token_data = exchange_code_for_token(code)
    if not token_data:
        logger.error("Failed to exchange code for token")
        return (
            "<h1>Authentication Failed</h1>"
            "<p>Could not complete Discord authentication.</p>"
            "<p>Make sure DISCORD_CLIENT_SECRET is set correctly in .env</p>"
        ), 400

    # Get user info
    access_token = token_data.get('access_token')
    user_info = get_user_info(access_token)
    if not user_info:
        logger.error("Failed to get user info")
        return "<h1>Authentication Failed</h1><p>Could not get user information.</p>", 400

    user_id = user_info.get('id')
    username = user_info.get('username')
    avatar = user_info.get('avatar')

    # Check if user has required role
    bot_token = discord_token()
    if not check_user_has_role(user_id, bot_token):
        logger.warning(f"User {username} ({user_id}) denied - missing required role")
        logout_url = url_for('logout')
        return (
            '<div style="font-family: sans-serif; max-width: 600px; margin: 100px auto; text-align: center;">'
            '<h1 style="color: #dc2626;">Access Denied</h1>'
            f'<p>Sorry <strong>{username}</strong>, you don\'t have the required role to access this dashboard.</p>'
            '<p style="color: #6b7280;">You need the <strong>"Loop 🎩"</strong> role in the Sapiopool Discord server.</p>'
            f'<a href="{logout_url}" style="display: inline-block; margin-top: 20px; padding: 10px 20px; '
            'background: #3b82f6; color: white; text-decoration: none; border-radius: 6px;">Try Different Account</a>'
            '</div>'
        ), 403

    # Create session
    session_id = create_session(user_id, username, avatar)

    # Redirect to original URL or home
    next_url = session.pop('next_url', url_for('index'))

    response = make_response(redirect(next_url))
    response.set_cookie(
        'cyber_session',
        session_id,
        max_age=30 * 24 * 60 * 60,  # 30 days
        httponly=True,
        samesite='Lax',
    )

    logger.info(f"User {username} ({user_id}) logged in successfully")
    return response


def _get_scraper_status() -> dict:
    """Check scraper logs for critical issues — cached 30s so we don't read the log on every request."""
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
                f.readline()  # skip partial line
            tail = f.read()
    except Exception:
        return {'ok': True}

    critical_patterns = [
        ('account/access', 'X session cookies expired — needs refresh'),
        ('security verification', 'Cloudflare blocking scraper — cookies need refresh'),
        ('Enable JavaScript and cookies', 'Cloudflare challenge — cookies need refresh'),
        ("Executable doesn't exist", 'Playwright browser not installed'),
    ]

    for pattern, message in critical_patterns:
        if pattern in tail:
            return {'ok': False, 'message': message}

    import re
    zero_found = len(re.findall(r'Found 0 tweet elements', tail))
    links_processed = len(re.findall(r'Processing link \d+/\d+', tail))
    if links_processed >= 3 and zero_found >= links_processed:
        return {'ok': False, 'message': 'Scraper finding no data — likely blocked by Cloudflare'}

    return {'ok': True}


@app.context_processor
def inject_user():
    """Inject current user into all templates."""
    user = get_current_user()
    if user:
        user['avatar_url'] = get_avatar_url(user.get('user_id'), user.get('avatar'))
    return {
        'current_user': user,
        'is_authenticated': is_authenticated(),
        'scraper_status': _get_scraper_status(),
    }


def _load_monthly_views(month_key: str) -> list[dict[str, str]]:
    path = MONTHLY_VIEWS_DIR / f"{month_key}-views.csv"
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "date": row.get("date", ""),
                "total_views": str(_as_int(row.get("total_views"))),
                "difference": str(_as_int(row.get("difference"))),
            })
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


def _load_monthly_actions(month_key: str) -> list[dict[str, str]]:
    path = MONTHLY_ACTIONS_DIR / f"{month_key}-actions.csv"
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "date": row.get("date", ""),
                "total_actions": str(_as_int(row.get("total_actions"))),
                "difference": str(_as_int(row.get("difference"))),
            })
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


def _get_scoped_tasks(month: str) -> list[dict]:
    if not members_service:
        return []
    return _cached(f'tasks:{month}', 60, lambda: members_service.get_tasks_for_month(month))


def _build_overview_stats(tasks: list[dict]) -> dict[str, int]:
    return {
        'impressions_total': sum(_as_int(task.get('impressions')) for task in tasks),
        'x_posts': sum(1 for t in tasks if t.get('platform') == 'x' and t.get('task_type') == 'content'),
        'reddit_posts': sum(1 for t in tasks if t.get('platform') == 'reddit' and t.get('task_type') == 'content'),
    }


def _prepare_content_posts(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    def get_impressions(task: dict) -> int:
        return _as_int(task.get('impressions'))

    content_tasks = [t for t in tasks if t.get('task_type') == 'content']
    content_tasks_sorted = sorted(content_tasks, key=get_impressions, reverse=True)

    for post in content_tasks_sorted:
        post["display_title"] = (
            post.get("title")
            or post.get("content")
            or post.get("description")
            or post.get("target_url")
            or "Untitled Post"
        )

    x_posts = [t for t in content_tasks_sorted if t.get('platform') == 'x']
    reddit_posts = [t for t in content_tasks_sorted if t.get('platform') == 'reddit']
    return x_posts, reddit_posts


def _get_performance_progress(month: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not month:
        return [], []
    return _load_monthly_views(month), _load_monthly_actions(month)


def _apply_member_profile_fallbacks(member: dict) -> None:
    x_handle = member.get('x_handle', '')
    if not x_handle or x_handle.lower() in ('active', 'inactive', ''):
        x_profile_url = member.get('x_profile_url', '')
        if x_profile_url:
            if 'x.com/' in x_profile_url or 'twitter.com/' in x_profile_url:
                member['x_handle'] = x_profile_url.rstrip('/').split('/')[-1]
            else:
                member['x_handle'] = x_profile_url.lstrip('@')


@app.route('/')
@login_required
def index():
    """Dashboard home - overview stats"""
    current_month = _current_month()
    try:
        selected_month = _requested_month(current_month)
        scoped_tasks = _get_scoped_tasks(selected_month)
        stats = _build_overview_stats(scoped_tasks)
        x_posts, reddit_posts = _prepare_content_posts(scoped_tasks)
        available_months = _cached('task_months', 60, members_service.get_available_task_months) if members_service else []

        performance_month = selected_month
        views_progress, actions_progress = _get_performance_progress(performance_month)
        return render_template(
            'index.html',
            stats=stats,
            x_posts=x_posts,
            reddit_posts=reddit_posts,
            current_month=current_month,
            selected_month=selected_month,
            available_months=available_months,
            views_progress=views_progress,
            actions_progress=actions_progress,
            performance_month=performance_month,
            performance_scope_label=performance_month or 'All Time',
            show_performance_charts=bool(performance_month),
        )
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return render_template(
            'index.html',
            stats={},
            x_posts=[],
            reddit_posts=[],
            available_months=[],
            views_progress=[],
            actions_progress=[],
            performance_month=current_month,
            performance_scope_label=current_month,
            show_performance_charts=True,
        )


@app.route('/members')
@login_required
def members():
    """Members page"""
    try:
        selected_month = _requested_month('')
        all_members = _cached('all_members', 60, members_service.get_all_members) if members_service else []
        available_months = _cached('activity_months', 60, members_service.get_available_activity_months) if members_service else []

        # Load all activity stats in 2 CSV reads (instead of 2 per member)
        _empty_stats = {'x_comments': 0, 'x_quotes': 0, 'x_retweets': 0, 'reddit_comments': 0, 'total_contributions': 0}
        all_stats = _cached(f'member_stats:{selected_month}', 60, lambda: members_service.get_all_member_stats(selected_month)) if members_service else {}

        for member in all_members:
            _apply_member_profile_fallbacks(member)
            discord_user = (member.get('discord_user') or '').lower()
            member.update(all_stats.get(discord_user, _empty_stats))

        all_members.sort(
            key=lambda m: (
                m.get('total_contributions', 0),
                (m.get('last_active') or ''),
                (m.get('discord_user') or '').lower(),
            ),
            reverse=True,
        )

        return render_template(
            'members.html',
            members=all_members,
            selected_month=selected_month,
            available_months=available_months,
            selected_scope_label=selected_month or 'All Time',
        )
    except Exception as e:
        logger.error(f"Error loading members: {e}")
        return render_template('members.html', members=[], selected_month='', available_months=[], selected_scope_label='All Time')


@app.route('/activity')
@login_required
def activity():
    """Activity history page"""
    try:
        month = _requested_month(_current_month())
        platform = request.args.get('platform', 'all').strip().lower()

        activities = _cached(f'activity:{month}', 60, lambda: members_service.get_combined_activity_history(month)) if members_service else []

        if platform != 'all':
            activities = [a for a in activities if a.get('platform') == platform]

        return render_template('activity.html',
                             activities=activities,
                             month=month,
                             platform=platform)
    except Exception as e:
        logger.error(f"Error loading activity: {e}")
        return render_template('activity.html', activities=[], month=datetime.now().strftime('%Y-%m'))


@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for dashboard stats"""
    try:
        selected_month = _requested_month(_current_month())
        stats = _build_overview_stats(_get_scoped_tasks(selected_month))

        return jsonify({
            'impressions_total': stats['impressions_total'],
            'x_posts': stats['x_posts'],
            'reddit_posts': stats['reddit_posts'],
            'month': selected_month,
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500


def _is_calendar_editor() -> bool:
    """Check if current user is allowed to edit calendar events."""
    import os
    user = get_current_user()
    if not user:
        return False
    editors_raw = os.environ.get('CALENDAR_EDITORS', '')
    if not editors_raw.strip():
        return False
    editors = [e.strip().lower() for e in editors_raw.split(',') if e.strip()]
    username = (user.get('username') or '').lower()
    return username in editors


def _load_calendar_events() -> list[dict]:
    path = Path(CALENDAR_DB)
    if not path.exists():
        return []
    events = []
    with path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            events.append(dict(row))
    events.sort(key=lambda e: e.get('date', ''), reverse=True)
    return events


def _save_calendar_events(events: list[dict]) -> None:
    path = Path(CALENDAR_DB)
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=CALENDAR_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(events)


def _enrich_events(events: list[dict]) -> list[dict]:
    enriched = []
    for ev in events:
        ev = dict(ev)
        ev['preparation_html'] = _render_markdown(ev.get('preparation_notes', ''))
        enriched.append(ev)
    return enriched


@app.route('/calendar')
@login_required
def calendar():
    """Calendar page — scheduled events."""
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
    new_event = {
        'id': str(uuid.uuid4()),
        'date': request.form.get('date', '').strip(),
        'title': request.form.get('title', '').strip(),
        'instructions': request.form.get('instructions', '').strip(),
        'preparation_notes': request.form.get('preparation_notes', '').strip(),
        'created_by': user.get('username', '') if user else '',
        'created_at': datetime.now().isoformat(),
    }
    events.append(new_event)
    _save_calendar_events(events)
    logger.info(f"Calendar event created: {new_event['title']}")
    return redirect(url_for('calendar'))


@app.route('/calendar/edit/<event_id>', methods=['POST'])
@login_required
def calendar_edit(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    events = _load_calendar_events()
    updated = []
    for ev in events:
        if ev.get('id') == event_id:
            ev = {
                **ev,
                'date': request.form.get('date', ev.get('date', '')).strip(),
                'title': request.form.get('title', ev.get('title', '')).strip(),
                'instructions': request.form.get('instructions', ev.get('instructions', '')).strip(),
                'preparation_notes': request.form.get('preparation_notes', ev.get('preparation_notes', '')).strip(),
            }
        updated.append(ev)
    _save_calendar_events(updated)
    return redirect(url_for('calendar'))


@app.route('/calendar/prep/<event_id>', methods=['POST'])
@login_required
def calendar_prep(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    events = _load_calendar_events()
    updated = []
    for ev in events:
        if ev.get('id') == event_id:
            ev = {**ev, 'preparation_notes': request.form.get('preparation_notes', '').strip()}
        updated.append(ev)
    _save_calendar_events(updated)
    return redirect(url_for('calendar'))


@app.route('/calendar/delete/<event_id>', methods=['POST'])
@login_required
def calendar_delete(event_id: str):
    if not _is_calendar_editor():
        return 'Forbidden', 403
    events = [ev for ev in _load_calendar_events() if ev.get('id') != event_id]
    _save_calendar_events(events)
    logger.info(f"Calendar event deleted: {event_id}")
    return redirect(url_for('calendar'))


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'version': '3.0',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    logger.info("Starting Dashboard 3.0 on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
