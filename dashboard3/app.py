#!/usr/bin/env python3
"""
Cybernetics Dashboard 3.0 - Signal Studio Edition
Clean, bold Flask web application for raid coordination analytics
"""

from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pathlib import Path
import sys

# Add project paths
_app_dir = Path(__file__).resolve().parent
_project_root = _app_dir.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root / "dashboard"))

from config import PROJECT_ROOT, DATABASE_DIR, flask_secret_key, load_env
from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

load_env()

logger = setup_logger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = flask_secret_key()

# Database paths
DB_DIR = DATABASE_DIR
MEMBERS_DB = str(DB_DIR / "members.csv")
LINKS_DB = str(DB_DIR / "links.csv")

# Initialize services
try:
    members_service = MembersDBService(MEMBERS_DB)
    links_service = LinksDBService(LINKS_DB)
    logger.info("Dashboard 3.0 - Services initialized")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    members_service = None
    links_service = None


@app.route('/')
def index():
    """Dashboard home - overview stats"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        selected_month = request.args.get('month', current_month)

        # Get overview stats for current month
        tasks = members_service.get_tasks_for_month(current_month) if members_service else []

        def parse_int(value):
            try:
                return int(str(value).replace(',', '').strip() or 0)
            except (TypeError, ValueError):
                return 0

        # Count posts from tasks (not activities)
        impressions_total = sum(parse_int(task.get('impressions')) for task in tasks)
        x_posts_count = len([t for t in tasks if t.get('platform') == 'x' and t.get('task_type') == 'content'])
        reddit_posts_count = len([t for t in tasks if t.get('platform') == 'reddit' and t.get('task_type') == 'content'])

        # Calculate stats
        stats = {
            'impressions_total': impressions_total,
            'x_posts': x_posts_count,
            'reddit_posts': reddit_posts_count,
        }

        # Get content posts for selected month (or all if no month selected)
        if members_service and selected_month == current_month:
            all_tasks = tasks
        else:
            all_tasks = members_service.get_tasks_for_month(selected_month) if members_service else []

        # Filter only content type tasks
        content_tasks = [t for t in all_tasks if t.get('task_type') == 'content']

        # Sort by impressions (convert to int, default to 0)
        def get_impressions(task):
            try:
                return int(str(task.get('impressions', 0)).replace(',', '').strip() or 0)
            except:
                return 0

        content_tasks_sorted = sorted(content_tasks, key=get_impressions, reverse=True)

        # Separate by platform
        x_posts = [t for t in content_tasks_sorted if t.get('platform') == 'x']
        reddit_posts = [t for t in content_tasks_sorted if t.get('platform') == 'reddit']

        # Get available months from all tasks
        if members_service and not selected_month:
            all_months_tasks = all_tasks
        else:
            all_months_tasks = members_service.get_tasks_for_month('') if members_service else []
        available_months = sorted(set(t.get('year_month') for t in all_months_tasks if t.get('year_month')), reverse=True)

        for post in x_posts + reddit_posts:
            post["display_title"] = (
                post.get("title")
                or post.get("content")
                or post.get("description")
                or post.get("target_url")
                or "Untitled Post"
            )

        return render_template(
            'index.html',
            stats=stats,
            x_posts=x_posts,
            reddit_posts=reddit_posts,
            current_month=current_month,
            selected_month=selected_month,
            available_months=available_months,
        )
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return render_template('index.html', stats={}, x_posts=[], reddit_posts=[], available_months=[])


@app.route('/members')
def members():
    """Members page"""
    try:
        all_members = members_service.get_all_members() if members_service else []

        # Calculate activity stats for each member
        for member in all_members:
            discord_user = member.get('discord_user')
            if not discord_user:
                continue

            # Get all activities for this member
            x_activities = members_service.get_x_activities_by_member(discord_user) if members_service else []
            reddit_activities = members_service.get_reddit_activities_by_member(discord_user) if members_service else []

            # Count activity types for X
            x_comments = len([a for a in x_activities if a.get('activity_type', '').lower() in ['comment', 'reply']])
            x_quotes = len([a for a in x_activities if a.get('activity_type', '').lower() == 'quote'])
            x_retweets = len([a for a in x_activities if a.get('activity_type', '').lower() in ['retweet', 'repost']])

            # Count Reddit comments
            reddit_comments = len([a for a in reddit_activities if a.get('activity_type', '').lower() in ['comment', 'reply']])

            # Add stats to member object
            member['x_comments'] = x_comments
            member['x_quotes'] = x_quotes
            member['x_retweets'] = x_retweets
            member['reddit_comments'] = reddit_comments
            member['total_contributions'] = x_comments + x_quotes + x_retweets + reddit_comments

        all_members.sort(
            key=lambda m: (
                m.get('total_contributions', 0),
                (m.get('last_active') or ''),
                (m.get('discord_user') or '').lower(),
            ),
            reverse=True,
        )

        return render_template('members.html', members=all_members)
    except Exception as e:
        logger.error(f"Error loading members: {e}")
        return render_template('members.html', members=[])


@app.route('/tasks')
def tasks():
    """Tasks page"""
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        all_tasks = members_service.get_tasks_for_month(month) if members_service else []
        for task in all_tasks:
            task["display_title"] = (
                task.get("title")
                or task.get("content")
                or task.get("description")
                or task.get("target_url")
                or task.get("task_id")
                or "Untitled Task"
            )
        return render_template('tasks.html', tasks=all_tasks, month=month)
    except Exception as e:
        logger.error(f"Error loading tasks: {e}")
        return render_template('tasks.html', tasks=[], month=datetime.now().strftime('%Y-%m'))


@app.route('/activity')
def activity():
    """Activity history page"""
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        platform = request.args.get('platform', 'all')

        activities = members_service.get_combined_activity_history(month) if members_service else []

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
def api_stats():
    """API endpoint for dashboard stats"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        tasks = members_service.get_tasks_for_month(current_month) if members_service else []
        activities = members_service.get_combined_activity_history(current_month) if members_service else []

        def parse_int(value):
            try:
                return int(str(value).replace(',', '').strip() or 0)
            except (TypeError, ValueError):
                return 0

        # Count posts from tasks (not activities)
        impressions_total = sum(parse_int(task.get('impressions')) for task in tasks)
        x_posts_count = len([t for t in tasks if t.get('platform') == 'x' and t.get('task_type') == 'content'])
        reddit_posts_count = len([t for t in tasks if t.get('platform') == 'reddit' and t.get('task_type') == 'content'])

        return jsonify({
            'impressions_total': impressions_total,
            'x_posts': x_posts_count,
            'reddit_posts': reddit_posts_count,
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'version': '3.0',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    logger.info("Starting Dashboard 3.0 on port 5004")
    app.run(host='0.0.0.0', port=5004, debug=False)
