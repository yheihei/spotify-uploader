"""
Pytest configuration and shared fixtures for Spotify Podcast Automation tests.
"""

import json
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture
def test_data_dir():
    """Return path to test data directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_episode_metadata():
    """Sample episode metadata for testing."""
    return {
        "slug": "20250618-test-episode",
        "title": "Test Episode",
        "description": "This is a test episode description",
        "pub_date": "2025-06-18T10:00:00+00:00",
        "duration_seconds": 1800,
        "file_size_bytes": 25000000,
        "mp3_url": "https://cdn.example.com/podcast/2025/20250618-test-episode.mp3",
        "guid": "repo-abc1234-20250618-test-episode",
        "s3_key": "podcast/2025/20250618-test-episode.mp3",
        "year": 2025
    }


@pytest.fixture
def invalid_episode_metadata():
    """Invalid episode metadata for testing validation."""
    return {
        "slug": "invalid-slug-format",
        "title": "",
        "description": None,
        "pub_date": "invalid-date",
        "duration_seconds": -1,
        "file_size_bytes": 0,
        "mp3_url": "not-a-valid-url",
        "guid": "invalid-guid",
        "s3_key": "invalid/path"
    }


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client."""
    mock_client = Mock()
    
    # Mock successful upload
    mock_client.upload_file.return_value = None
    
    # Mock head_object for verification
    mock_client.head_object.return_value = {
        'ContentLength': 25000000,
        'LastModified': datetime.now(timezone.utc),
        'Metadata': {
            'title': 'Test Episode',
            'description': 'Test description',
            'duration': '1800',
            'guid': 'test-guid'
        }
    }
    
    # Mock list_objects_v2 for RSS generation
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            'Contents': [
                {
                    'Key': 'podcast/2025/20250618-test-episode.mp3',
                    'Size': 25000000,
                    'LastModified': datetime.now(timezone.utc)
                }
            ]
        }
    ]
    
    # Mock put_object for RSS upload
    mock_client.put_object.return_value = None
    
    # Mock copy_object for atomic operations
    mock_client.copy_object.return_value = None
    
    # Mock delete_object for cleanup
    mock_client.delete_object.return_value = None
    
    # Mock head_bucket for bucket verification
    mock_client.head_bucket.return_value = None
    
    return mock_client


@pytest.fixture
def mock_spotify_api():
    """Mock Spotify API responses."""
    mock_session = Mock()
    
    # Mock authentication response
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {
        'access_token': 'mock_access_token',
        'expires_in': 3600
    }
    
    # Mock episodes API response
    episodes_response = Mock()
    episodes_response.status_code = 200
    episodes_response.json.return_value = {
        'items': [
            {
                'id': 'mock_episode_id',
                'name': 'Test Episode',
                'description': 'Contains test GUID: repo-abc1234-20250618-test-episode',
                'external_urls': {
                    'spotify': 'https://open.spotify.com/episode/mock_episode_id'
                }
            }
        ],
        'next': None
    }
    
    # Mock show info response
    show_response = Mock()
    show_response.status_code = 200
    show_response.json.return_value = {
        'id': 'mock_show_id',
        'name': 'Test Podcast',
        'description': 'Test podcast description'
    }
    
    mock_session.post.return_value = auth_response
    mock_session.get.return_value = episodes_response
    
    return mock_session


@pytest.fixture
def temporary_mp3_file():
    """Create a temporary MP3-like file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        # Write some dummy MP3-like data
        tmp_file.write(b'ID3\x03\x00\x00\x00' + b'0' * 1000)  # Minimal MP3 header + data
        tmp_file.flush()
        yield tmp_file.name
    
    # Cleanup
    try:
        os.unlink(tmp_file.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def temporary_directory():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def mock_mutagen_file():
    """Mock mutagen audio file object."""
    mock_file = Mock()
    mock_file.info.length = 1800.0  # 30 minutes
    mock_file.tags = {
        'TIT2': ['Test Episode Title'],
        'COMM::eng': ['Test episode description'],
    }
    return mock_file


@pytest.fixture
def mock_environment_variables(monkeypatch):
    """Mock environment variables for testing."""
    env_vars = {
        'AWS_REGION': 'us-east-1',
        'AWS_S3_BUCKET': 'test-podcast-bucket',
        'SPOTIFY_CLIENT_ID': 'test_client_id',
        'SPOTIFY_CLIENT_SECRET': 'test_client_secret',
        'SPOTIFY_REFRESH_TOKEN': 'test_refresh_token',
        'SPOTIFY_SHOW_ID': 'test_show_id',
        'BASE_URL': 'https://cdn.test.com',
        'PODCAST_TITLE': 'Test Podcast',
        'PODCAST_DESCRIPTION': 'Test podcast description',
        'PODCAST_AUTHOR': 'Test Author',
        'PODCAST_EMAIL': 'test@example.com',
        'GITHUB_REPOSITORY': 'user/test-repo',
        'GITHUB_RUN_ID': '12345',
        'GITHUB_SERVER_URL': 'https://github.com',
        'GITHUB_ACTOR': 'testuser'
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture
def rss_feed_xml():
    """Sample RSS feed XML for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test Podcast</title>
    <description>Test podcast description</description>
    <link>https://cdn.test.com</link>
    <language>ja</language>
    <lastBuildDate>Mon, 18 Jun 2025 10:00:00 +0000</lastBuildDate>
    <item>
      <title>Test Episode</title>
      <description>Test episode description</description>
      <guid>repo-abc1234-20250618-test-episode</guid>
      <pubDate>Mon, 18 Jun 2025 10:00:00 +0000</pubDate>
      <enclosure url="https://cdn.test.com/podcast/2025/20250618-test-episode.mp3" 
                 length="25000000" type="audio/mpeg"/>
    </item>
  </channel>
</rss>'''


@pytest.fixture
def mock_github_actions_output(monkeypatch):
    """Mock GitHub Actions output for testing."""
    outputs = {}
    
    def mock_print(*args, **kwargs):
        for arg in args:
            if '::set-output' in str(arg):
                # Parse GitHub Actions output format
                parts = str(arg).split('::set-output name=')[1].split('::')
                if len(parts) == 2:
                    key, value = parts
                    outputs[key] = value
    
    monkeypatch.setattr('builtins.print', mock_print)
    return outputs