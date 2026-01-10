-- Members DB Schema - Member profiles and activity tracking

CREATE TABLE IF NOT EXISTS members (
    discord_user VARCHAR(100) PRIMARY KEY,
    x_handle VARCHAR(100),
    reddit_username VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    joined_date DATE,
    last_activity DATE,
    total_points INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS coordinated_tasks (
    task_id VARCHAR(50) PRIMARY KEY,
    platform VARCHAR(10) NOT NULL,
    task_type VARCHAR(50),
    target_url VARCHAR(500),
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_date DATE,
    created_by VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS x_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    time TIME NOT NULL,
    discord_user VARCHAR(100) NOT NULL,
    x_handle VARCHAR(100),
    activity_type VARCHAR(50),
    activity_url VARCHAR(500),
    target_url VARCHAR(500),
    task_id VARCHAR(50),
    impressions INTEGER DEFAULT 0,
    engagement INTEGER DEFAULT 0,
    notes TEXT,
    UNIQUE(discord_user, activity_url)
);

CREATE TABLE IF NOT EXISTS reddit_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    time TIME NOT NULL,
    discord_user VARCHAR(100) NOT NULL,
    reddit_username VARCHAR(100),
    activity_type VARCHAR(50),
    activity_url VARCHAR(500),
    target_url VARCHAR(500),
    task_id VARCHAR(50),
    upvotes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    notes TEXT,
    UNIQUE(discord_user, activity_url)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);
CREATE INDEX IF NOT EXISTS idx_x_activity_discord_user ON x_activity_log(discord_user);
CREATE INDEX IF NOT EXISTS idx_x_activity_date ON x_activity_log(date);
CREATE INDEX IF NOT EXISTS idx_x_activity_task ON x_activity_log(task_id);
CREATE INDEX IF NOT EXISTS idx_reddit_activity_discord_user ON reddit_activity_log(discord_user);
CREATE INDEX IF NOT EXISTS idx_reddit_activity_date ON reddit_activity_log(date);
CREATE INDEX IF NOT EXISTS idx_reddit_activity_task ON reddit_activity_log(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_active ON coordinated_tasks(is_active);
