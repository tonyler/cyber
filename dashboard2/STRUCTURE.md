# Dashboard 2.0 - Project Structure

```
dashboard2/
├── app.py                  # Flask application (main entry point)
├── requirements.txt        # Python dependencies (Flask)
├── run.sh                 # Quick start script
├── README.md              # Getting started guide
├── FEATURES.md            # Feature overview & comparison
├── STRUCTURE.md           # This file
│
├── templates/             # Jinja2 HTML templates
│   ├── base.html         # Base layout (nav, footer, meta)
│   ├── index.html        # Dashboard home (stats + recent activity)
│   ├── members.html      # Members directory (grid of cards)
│   ├── tasks.html        # Tasks list (with month filter)
│   └── activity.html     # Activity history (with platform filter)
│
└── static/               # Static assets
    ├── css/
    │   └── style.css     # Custom styles (animations, components)
    └── js/
        └── main.js       # JavaScript (mobile menu, shortcuts, utils)
```

## File Responsibilities

### app.py
- Flask app initialization
- Route handlers for all pages
- Service layer integration
- API endpoints
- Health checks

**Routes:**
- `GET /` - Dashboard home
- `GET /members` - Members page
- `GET /tasks?month=` - Tasks page with filter
- `GET /activity?month=&platform=` - Activity with filters
- `GET /api/stats` - JSON stats endpoint
- `GET /health` - Health check

### templates/base.html
- HTML5 structure
- Tailwind CSS CDN
- Google Fonts (Inter)
- Navigation bar (desktop + mobile)
- Footer with status indicator
- Block system for content injection

**Blocks:**
- `{% block title %}` - Page title
- `{% block content %}` - Main content area
- `{% block extra_js %}` - Additional scripts

### templates/index.html
- 4 stat cards (members, tasks, X, Reddit)
- Recent activity feed (10 items)
- Platform badges
- Quick links

### templates/members.html
- Grid layout (3 columns desktop, 1 mobile)
- Member cards with avatars
- Social handles (X + Reddit)
- Activity stats
- Status badges

### templates/tasks.html
- Month filter form
- Task list with details
- Platform/type badges
- Active status indicator
- Engagement metrics (impressions, likes, comments)
- Clickable target URLs

### templates/activity.html
- Combined filter form (month + platform)
- Activity timeline
- Platform icons
- User info + timestamps
- Activity links (activity + target)
- Notes display

### static/css/style.css
- Custom component styles
- Animation definitions
- Hover effects
- Responsive utilities
- Print styles
- Custom scrollbar

**Key Classes:**
- `.stat-card` - Stat card with hover lift
- `.member-card` - Member profile card
- `.task-card` - Task item card
- `.activity-item` - Activity list item
- `.nav-link` - Navigation link style

### static/js/main.js
- Mobile menu toggle
- Keyboard shortcuts (Alt+H/M/T/A)
- Form loading states
- Toast notifications
- Smooth scrolling
- Lazy loading
- Performance monitoring

**Utilities:**
- `showToast(message, type)` - Display toast notification
- `copyToClipboard(text)` - Copy text to clipboard

## Data Flow

```
User Request
    ↓
Flask Route (app.py)
    ↓
Service Layer (members_service.py, links_service.py)
    ↓
CSV Files (database/*.csv)
    ↓
Template Rendering (Jinja2)
    ↓
HTML Response
```

## Service Integration

Dashboard 2.0 uses the existing service layer:
- `members_service.py` - Member & activity data
- `links_service.py` - Links management
- `csv_store.py` - CSV operations
- `logger_config.py` - Logging

**Key Service Methods Used:**
- `get_all_members()` - All members
- `get_active_members()` - Active only
- `get_tasks_for_month(month)` - Tasks by month
- `get_combined_activity_history(month)` - All activities

## Styling Approach

**Utility-First (Tailwind)**
- Rapid development
- Consistent spacing/colors
- Responsive utilities
- No CSS bloat

**Custom CSS (style.css)**
- Component-specific styles
- Complex animations
- Hover effects
- Global overrides

**Best of Both Worlds**
- Tailwind for layout/spacing
- Custom CSS for polish

## Extension Points

Want to add features? Here's where:

**New Page**
1. Add route in `app.py`
2. Create template in `templates/`
3. Add nav link in `base.html`

**New Component**
1. Add HTML in template
2. Add styles in `style.css`
3. Add interactions in `main.js`

**New API Endpoint**
1. Add route in `app.py`
2. Return `jsonify(data)`
3. Call from frontend JS

**Custom Styling**
1. Extend Tailwind config in `base.html`
2. Or add to `style.css`

## Dependencies

**Python:**
- Flask 3.0.0 (web framework)
- Existing project services

**Frontend:**
- Tailwind CSS 3.x (via CDN)
- Inter font (Google Fonts)
- Vanilla JavaScript (no frameworks)

**Data:**
- CSV files (no database)
- File-based storage
- Portable across systems

## Deployment

**Local Development:**
```bash
pip install -r requirements.txt
python3 app.py
# Visit http://localhost:5003
```

**Production:**
- Use WSGI server (gunicorn, waitress)
- Set `debug=False` in app.py
- Configure proper logging
- Set up reverse proxy (nginx)

**Environment:**
- Python 3.11+
- Any OS (Linux, macOS, Windows)
- No special system requirements

---

Simple. Portable. Professional.
