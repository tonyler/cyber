# Mobile X Scraper - Testing & Setup Guide

## Quick Test Commands

### Test with browser visible (recommended first)
```bash
cd /root/cyber/scrapers
python3 run_scrapers.py --x --limit 1 --no-headless --verbose-metrics
```

### Progressive testing
```bash
# After confirming basic functionality works:
python3 run_scrapers.py --x --limit 5 --verbose-metrics    # Test 5 links
python3 run_scrapers.py --x --limit 20 --verbose-metrics   # Larger test
python3 run_scrapers.py --x                                 # Full run (headless)
```

## What to Look For

When testing with `--no-headless`:
- Browser window should be **narrow** (iPhone-sized: 390×844)
- X.com should display **mobile interface** (not desktop)
- Check console logs for "mobile mode" messages
- Debug logs show which selectors succeeded

## Transferring X Session to Another Computer

### Session File Location
```
/root/cyber/shared/x_session.json
```

### Transfer Methods

**Option 1: Copy/Paste**
```bash
# On this computer - display the session file
cat /root/cyber/shared/x_session.json

# Copy the output, then on the other computer create the file:
mkdir -p /path/to/cyber/shared
nano /path/to/cyber/shared/x_session.json
# Paste the content and save
```

**Option 2: SCP (if SSH access available)**
```bash
# From the other computer
scp user@this-server:/root/cyber/shared/x_session.json /path/to/cyber/shared/x_session.json
```

### Session Notes
- Same session works on multiple computers
- Works with both desktop and mobile scrapers
- Sessions typically valid for 30-90 days
- **Keep this file private** - contains authentication tokens

## Mobile Scraper Changes

### What Changed
- Viewport: 1920×1080 → 390×844 (iPhone 14 Pro)
- User Agent: Desktop Chrome → iOS Safari
- Scroll timing: Faster (2.0s default, 1.5s for quotes/reposts)
- Added mobile fallback selectors with debug logging

### Expected Benefits
- 15-30% faster scraping
- Simpler DOM structure
- Better performance
- Easier to maintain

## Troubleshooting

If selectors fail:
1. Run with `--no-headless` to see actual mobile DOM
2. Use browser DevTools to inspect element structure
3. Check debug logs to see which selectors failed
4. Update selectors in `x_scraper.py` if needed

Session not working:
1. Check if `auth_token` cookie exists in session file
2. Verify session file path is correct
3. Try regenerating session if expired
