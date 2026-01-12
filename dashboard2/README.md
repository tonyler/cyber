# Cybernetics Dashboard 2.0

Modern, professional dashboard for raid coordination and member activity tracking.

## Features

- **Clean, Modern Design**: Professional gradient-based UI with smooth animations
- **Responsive Layout**: Works perfectly on desktop, tablet, and mobile devices
- **Real-time Stats**: Overview of members, tasks, and platform activities
- **Activity Tracking**: Monitor X/Twitter and Reddit contributions
- **Task Management**: View and filter coordinated raid tasks
- **Member Directory**: Complete member profiles with stats

## Quick Start

1. **Install dependencies** (first time only):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start the dashboard**:
   ```bash
   ./start.sh
   ```

3. **Open in browser**:
   ```
   http://your-server-ip:5003
   ```

4. **Stop the dashboard**:
   ```bash
   ./stop.sh
   ```

**Note**: Port 5003 must be open in your firewall. Run `sudo ufw allow 5003/tcp` if needed.

## Pages

- **Dashboard** (`/`) - Overview with key stats and recent activity
- **Members** (`/members`) - All registered members with profiles
- **Tasks** (`/tasks`) - Coordinated tasks with month filtering
- **Activity** (`/activity`) - Complete activity history with platform filters

## Tech Stack

- **Backend**: Flask (Python 3.11+)
- **Frontend**: Tailwind CSS + Vanilla JavaScript
- **Data**: CSV files (portable, no database required)
- **Fonts**: Inter (Google Fonts)

## Design Principles

- Simple, clean, professional
- Smooth animations and transitions
- Accessibility-focused
- Fast loading and performance
- Mobile-first responsive design

## Keyboard Shortcuts

- `Alt + H` - Go to Home/Dashboard
- `Alt + M` - Go to Members
- `Alt + T` - Go to Tasks
- `Alt + A` - Go to Activity

## Portability

This dashboard is fully portable and uses relative paths throughout. Just ensure:
- The `database/` directory exists in the project root
- CSV files are in place (members.csv, links.csv, etc.)

## Development

The dashboard automatically reloads when files change (when `debug=True` in app.py).

## API Endpoints

- `GET /api/stats` - Get dashboard statistics
- `GET /health` - Health check endpoint

---

Built with ⚡ for The Cybernetics
