# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 応答ルール

日本語で応答すること

## Project Overview

This is a **Spotify Podcast Automation System** that eliminates manual operations for podcast episode uploads. The system automates the entire workflow from audio file upload to Spotify availability confirmation via RSS feed generation and GitHub Actions CI/CD.

**Key Architecture:**
- Upload MP3 files to AWS S3 with public access
- Generate RSS feeds using Python `feedgen` library
- Deploy via GitHub Actions with automatic Spotify indexing verification
- Complete workflow must execute within 2 minutes on GitHub Actions

## Development Commands

Since this is a Python-based project, common commands will be:

```bash
# Install dependencies (when requirements.txt is created)
pip install -r requirements.txt

# Run RSS generation script
python scripts/build_rss.py

# Run Spotify verification script  
python scripts/check_spotify.py

# Run tests
pytest

# Test GitHub Actions workflow locally (if act is used)
act -j release
```

## Core System Requirements

**Critical Performance Constraints:**
- GitHub Actions workflow execution ≤ 2 minutes total
- Spotify indexing verification within 15 minutes average
- All operations must be idempotent for safe re-runs

**Required Integrations:**
- AWS S3 for audio file storage and RSS hosting
- Spotify Web API for episode verification
- GitHub Actions for CI/CD automation

**Key Technical Patterns:**
- Use atomic file replacement for RSS updates (`rss.xml.new` → rename)
- Implement retry logic with max 3 attempts for S3 operations
- Poll Spotify API with 30-second intervals, maximum 10 times
- Generate unique episode GUIDs using format: `repo-{sha}-{slug}`

## File Structure

```
├── .github/workflows/release.yml    # Main automation workflow
├── scripts/
│   ├── build_rss.py                # RSS generation with feedgen
│   └── check_spotify.py            # Spotify API verification
├── episodes/                       # MP3 files trigger workflow
└── .docs/prd/seed.md               # Comprehensive Japanese PRD with full requirements
```

## Authentication & Security

**Required GitHub Secrets:**
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for S3 access
- Spotify OAuth token with minimal TTL using Refresh Token pattern

**Security Considerations:**
- All S3 objects must be publicly accessible (no signed URLs - Spotify requires direct access)
- Cache-Control headers set to `public, max-age=300` for RSS and MP3 files

## Data Formats

**Episode Naming Convention:**
- Slug format: `YYYYMMDD-title-kebab` (e.g., `20250618-automation-pipeline`)
- S3 path: `podcast/{YYYY}/{slug}.mp3`

**RSS Requirements:**
- Must include all episodes in single feed
- Update `<lastBuildDate>` on each generation
- Ensure valid XML structure for Spotify compatibility

## Testing Strategy

- RSS generation scripts must have `pytest` coverage
- Include acceptance tests for complete workflow scenarios
- Test idempotent behavior with duplicate GUID scenarios
- Verify S3 upload retry logic under failure conditions