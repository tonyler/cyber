#!/usr/bin/env python3
"""
Cybernetics Dashboard - Flask Web Application
Displays member activity stats and history
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "dashboard"))

from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

logger = setup_logger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cybernetics-dashboard-secret-key'

# Database paths
DB_DIR = project_root / "database"
MEMBERS_DB = str(DB_DIR / "members.csv")
LINKS_DB = str(DB_DIR / "links.csv")

# Initialize services
try:
    members_service = MembersDBService(MEMBERS_DB)
    links_service = LinksDBService(LINKS_DB)
    logger.info("Database services initialized")
except Exception as e:
    logger.error(f"Failed to initialize database services: {e}")
    members_service = None
    links_service = None

@app.route('/')
def index():
    """Home page - redirect to history page"""
    from flask import redirect, url_for
    return redirect(url_for('history_page'))

@app.route('/content')
def content_page():
    """Content tasks page"""
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        tasks = members_service.get_tasks_for_month(month) if members_service else []

        return render_template('content_page.html',
                               tasks=tasks,
                               month=month)
    except Exception as e:
        logger.error(f"Error loading content page: {e}")
        return render_template('content_page.html', tasks=[], month=datetime.now().strftime('%Y-%m'))

@app.route('/x')
def x_page():
    """Legacy X/Twitter route"""
    return redirect(url_for('content_page'))

@app.route('/reddit')
def reddit_page():
    """Reddit activity page"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        activities = members_service.get_combined_activity_history(current_month) if members_service else []
        reddit_activities = [a for a in activities if a.get('platform') == 'reddit']

        return render_template('history_page.html',
                             activities=reddit_activities,
                             platform='Reddit',
                             month=current_month)
    except Exception as e:
        logger.error(f"Error loading Reddit page: {e}")
        return render_template('history_page.html', activities=[], platform='Reddit')

@app.route('/total')
def total_page():
    """Total activity page"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        activities = members_service.get_combined_activity_history(current_month) if members_service else []

        return render_template('history_page.html',
                             activities=activities,
                             platform='Total',
                             month=current_month)
    except Exception as e:
        logger.error(f"Error loading total page: {e}")
        return render_template('history_page.html', activities=[], platform='Total')

@app.route('/history')
def history_page():
    """History page with month selector"""
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        platform_filter = request.args.get('platform', 'all').lower()

        activities = members_service.get_combined_activity_history(month) if members_service else []

        if platform_filter != 'all':
            activities = [a for a in activities if a.get('platform') == platform_filter]

        return render_template('history_page.html',
                             activities=activities,
                             month=month,
                             platform=platform_filter.title(),
                             form_action=url_for('history_page'))
    except Exception as e:
        logger.error(f"Error loading history page: {e}")
        return render_template('history_page.html', activities=[], form_action=url_for('history_page'))

@app.route('/search')
def search_page():
    """Search page for members and activities"""
    try:
        query = request.args.get('q', '').strip()
        results = []

        if query and members_service:
            # Search members
            all_members = members_service.get_all_members()
            results = [m for m in all_members if query.lower() in m.get('discord_user', '').lower()]

        return render_template('search_page.html',
                             query=query,
                             results=results)
    except Exception as e:
        logger.error(f"Error loading search page: {e}")
        return render_template('search_page.html', query='', results=[])

@app.route('/api/members')
def api_members():
    """API endpoint for members data"""
    try:
        if not members_service:
            return jsonify({'error': 'Members service not available'}), 500

        members = members_service.get_all_members()
        return jsonify({'members': members})
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/activities/<month>')
def api_activities(month):
    """API endpoint for activity data"""
    try:
        if not members_service:
            return jsonify({'error': 'Members service not available'}), 500

        activities = members_service.get_combined_activity_history(month)
        return jsonify({'activities': activities, 'month': month})
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    status = {
        'status': 'healthy',
        'members_db': 'connected' if members_service else 'disconnected',
        'links_db': 'connected' if links_service else 'disconnected',
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(status)

if __name__ == '__main__':
    logger.info("Starting Cybernetics Dashboard on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
