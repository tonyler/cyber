-- Links DB Schema - Per-month indexed archive
-- Individual post records with year_month tag (MANDATORY in every query)

CREATE TABLE IF NOT EXISTS all_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month VARCHAR(7) NOT NULL,  -- Format: "2025-12" - MANDATORY in every query
    date DATE,
    platform VARCHAR(10) NOT NULL,   -- Either "x" or "reddit"
    author VARCHAR(100),
    url VARCHAR(500) NOT NULL,
    impressions_or_views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,         -- X: Likes, Reddit: Upvotes
    comments INTEGER DEFAULT 0,      -- Comments/Replies
    retweets INTEGER DEFAULT 0,      -- X: Retweets, Reddit: 0
    notes TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast per-month lookups (CRITICAL)
CREATE INDEX IF NOT EXISTS idx_year_month ON all_links(year_month);
CREATE INDEX IF NOT EXISTS idx_year_month_platform ON all_links(year_month, platform);
CREATE INDEX IF NOT EXISTS idx_url ON all_links(url);
CREATE INDEX IF NOT EXISTS idx_author ON all_links(author);
