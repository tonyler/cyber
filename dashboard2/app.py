#!/usr/bin/env python3
"""
Cybernetics Dashboard 2.0 - Modern Professional Edition
Clean, minimal Flask web application for raid coordination analytics
"""

from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pathlib import Path
import sys

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "dashboard"))

from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

logger = setup_logger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cyber-dashboard-2-secret'

# Database paths (relative to project root)
DB_DIR = project_root / "database"
MEMBERS_DB = str(DB_DIR / "members.csv")
LINKS_DB = str(DB_DIR / "links.csv")

# Initialize services
try:
    members_service = MembersDBService(MEMBERS_DB)
    links_service = LinksDBService(LINKS_DB)
    logger.info("Dashboard 2.0 - Services initialized")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    members_service = None
    links_service = None


@app.route('/')
def index():
    """Dashboard home - overview stats"""
    try:
        current_month = datetime.now().strftime('%Y-%m')

        # Get overview stats
        tasks = members_service.get_tasks_for_month(current_month) if members_service else []
        activities = members_service.get_combined_activity_history(current_month) if members_service else []

        def parse_int(value):
            try:
                return int(str(value).replace(',', '').strip() or 0)
            except (TypeError, ValueError):
                return 0

        def is_content_activity(activity):
            activity_type = (activity.get('activity_type') or '').strip().lower()
            return activity_type not in {'comment', 'reply', 'quote', 'repost', 'retweet'}

        impressions_total = sum(parse_int(task.get('impressions')) for task in tasks)
        content_activities = [a for a in activities if is_content_activity(a)]
        x_posts = [a for a in content_activities if a.get('platform') == 'x']
        reddit_posts = [a for a in content_activities if a.get('platform') == 'reddit']

        # Calculate stats
        stats = {
            'impressions_total': impressions_total,
            'x_posts': len(x_posts),
            'reddit_posts': len(reddit_posts),
        }

        # Get all tasks (not just current month) and sort by impressions
        all_tasks = members_service.get_tasks_for_month('') if members_service else []

        # Sort tasks by impressions (convert to int, default to 0)
        def get_impressions(task):
            try:
                return int(str(task.get('impressions', 0)).replace(',', '').strip() or 0)
            except:
                return 0

        top_posts = sorted(all_tasks, key=get_impressions, reverse=True)[:10]

        return render_template('index.html',
                             stats=stats,
                             top_posts=top_posts,
                             current_month=current_month)
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return render_template('index.html', stats={}, top_posts=[])


@app.route('/members')
def members():
    """Members page"""
    try:
        all_members = members_service.get_all_members() if members_service else []
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

        def is_content_activity(activity):
            activity_type = (activity.get('activity_type') or '').strip().lower()
            return activity_type not in {'comment', 'reply', 'quote', 'repost', 'retweet'}

        impressions_total = sum(parse_int(task.get('impressions')) for task in tasks)
        content_activities = [a for a in activities if is_content_activity(a)]
        x_posts = [a for a in content_activities if a.get('platform') == 'x']
        reddit_posts = [a for a in content_activities if a.get('platform') == 'reddit']

        return jsonify({
            'impressions_total': impressions_total,
            'x_posts': len(x_posts),
            'reddit_posts': len(reddit_posts),
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    logger.info("Starting Dashboard 2.0 on port 5003")
    app.run(host='0.0.0.0', port=5003, debug=False)
