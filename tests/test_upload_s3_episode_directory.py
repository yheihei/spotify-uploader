"""
Tests for S3 upload script episode directory functionality (upload_s3.py).

This module tests the episode directory upload functionality including:
- Directory structure upload
- Multiple file type handling
- Content type detection
- Metadata application
- Error handling
"""

import os
import json
import tempfile
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from upload_s3 import S3Uploader


class TestS3UploaderDirectoryFeatures:
    """Test cases for S3Uploader directory functionality."""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client."""
        mock_client = Mock()
        mock_client.upload_file = Mock()
        mock_client.head_object = Mock(return_value={'ContentLength': 1000})
        mock_client.head_bucket = Mock()
        return mock_client
    
    @pytest.fixture
    def uploader(self, mock_s3_client):
        """Create S3Uploader instance with mock client."""
        uploader = S3Uploader.__new__(S3Uploader)
        uploader.bucket_name = 'test-bucket'
        uploader.s3_client = mock_s3_client
        return uploader
    
    def test_get_content_type(self, uploader):
        """Test content type detection for various file types."""
        test_cases = [
            ('audio.mp3', 'audio/mpeg'),
            ('episode.wav', 'audio/wav'),
            ('cover.jpg', 'image/jpeg'),
            ('thumb.jpeg', 'image/jpeg'),
            ('image.png', 'image/png'),
            ('animated.gif', 'image/gif'),
            ('modern.webp', 'image/webp'),
            ('data.json', 'application/json'),
            ('unknown.xyz', 'application/octet-stream')
        ]
        
        for filename, expected_type in test_cases:
            assert uploader._get_content_type(filename) == expected_type
    
    def test_generate_episode_s3_path(self, uploader):
        """Test S3 path generation for episodes."""
        pub_date = datetime(2025, 6, 18)
        
        path = uploader.generate_episode_s3_path('20250618-test-episode', pub_date)
        assert path == 'podcast/2025/20250618-test-episode'
        
        # Test different years
        path = uploader.generate_episode_s3_path('20241231-year-end', datetime(2024, 12, 31))
        assert path == 'podcast/2024/20241231-year-end'
    
    def test_upload_episode_directory_success(self, uploader):
        """Test successful episode directory upload."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory with files
            episode_dir = os.path.join(temp_dir, 'test-episode')
            os.makedirs(episode_dir)
            
            # Create test files
            files_to_create = [
                ('audio.mp3', 'audio content'),
                ('cover.jpg', 'image content'),
                ('episode_data.json', '{"title": "Test Episode"}')
            ]
            
            for filename, content in files_to_create:
                with open(os.path.join(episode_dir, filename), 'w') as f:
                    f.write(content)
            
            # Mock successful upload for each file
            def mock_upload_with_retry(local_file, s3_key, metadata=None):
                filename = os.path.basename(local_file)
                return {
                    'success': True,
                    'bucket': 'test-bucket',
                    's3_key': s3_key,
                    'file_size': len(filename) * 100,  # Mock size
                    'upload_duration': 0.5,
                    'attempts': 1,
                    'url': f'https://test-bucket.s3.amazonaws.com/{s3_key}'
                }
            
            uploader.upload_with_retry = mock_upload_with_retry
            
            # Test upload
            result = uploader.upload_episode_directory(
                episode_dir=episode_dir,
                base_s3_path='podcast/2025/test-episode',
                episode_metadata={'title': 'Test Episode', 'duration': '300'}
            )
            
            # Verify results
            assert result['success'] is True
            assert result['total_files'] == 3
            assert result['failed_files'] == 0
            
            # Check audio file tracking
            assert result['audio_file'] is not None
            assert result['audio_file']['filename'] == 'audio.mp3'
            assert result['audio_file']['s3_key'] == 'podcast/2025/test-episode/audio.mp3'
            
            # Check episode image tracking
            assert result['episode_image'] is not None
            assert result['episode_image']['filename'] == 'cover.jpg'
            assert result['episode_image']['s3_key'] == 'podcast/2025/test-episode/cover.jpg'
            
            # Check file results
            assert 'audio.mp3' in result['files']
            assert 'cover.jpg' in result['files']
            assert 'episode_data.json' in result['files']
            
            for filename, file_result in result['files'].items():
                assert file_result['success'] is True
    
    def test_upload_episode_directory_partial_failure(self, uploader):
        """Test episode directory upload with some file failures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, 'test-episode')
            os.makedirs(episode_dir)
            
            # Create test files
            for filename in ['audio.mp3', 'cover.jpg', 'data.json']:
                with open(os.path.join(episode_dir, filename), 'w') as f:
                    f.write('content')
            
            # Mock upload with one failure
            def mock_upload_with_retry(local_file, s3_key, metadata=None):
                filename = os.path.basename(local_file)
                if filename == 'cover.jpg':
                    return {
                        'success': False,
                        'error': 'Upload failed',
                        'attempts': 3
                    }
                else:
                    return {
                        'success': True,
                        'bucket': 'test-bucket',
                        's3_key': s3_key,
                        'file_size': 1000,
                        'upload_duration': 0.5,
                        'attempts': 1,
                        'url': f'https://test-bucket.s3.amazonaws.com/{s3_key}'
                    }
            
            uploader.upload_with_retry = mock_upload_with_retry
            
            # Test upload
            result = uploader.upload_episode_directory(
                episode_dir=episode_dir,
                base_s3_path='podcast/2025/test-episode'
            )
            
            # Verify results
            assert result['success'] is False
            assert result['total_files'] == 3
            assert result['failed_files'] == 1
            
            # Check that audio file was still tracked despite other failures
            assert result['audio_file'] is not None
            assert result['audio_file']['filename'] == 'audio.mp3'
            
            # Episode image should be None due to upload failure
            assert result['episode_image'] is None
    
    def test_upload_episode_directory_no_files(self, uploader):
        """Test episode directory upload with empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create empty episode directory
            episode_dir = os.path.join(temp_dir, 'empty-episode')
            os.makedirs(episode_dir)
            
            # Test upload
            result = uploader.upload_episode_directory(
                episode_dir=episode_dir,
                base_s3_path='podcast/2025/empty-episode'
            )
            
            # Should still succeed but with no files
            assert result['success'] is True
            assert result['total_files'] == 0
            assert result['failed_files'] == 0
            assert result['audio_file'] is None
            assert result['episode_image'] is None
    
    def test_upload_episode_directory_nonexistent(self, uploader):
        """Test episode directory upload with nonexistent directory."""
        with pytest.raises(FileNotFoundError, match="Episode directory not found"):
            uploader.upload_episode_directory(
                episode_dir='/nonexistent/directory',
                base_s3_path='podcast/2025/nonexistent'
            )
    
    def test_upload_episode_directory_not_directory(self, uploader):
        """Test episode directory upload with file instead of directory."""
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValueError, match="Path is not a directory"):
                uploader.upload_episode_directory(
                    episode_dir=temp_file.name,
                    base_s3_path='podcast/2025/not-dir'
                )
    
    def test_upload_episode_directory_metadata_application(self, uploader):
        """Test that episode metadata is applied to audio files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory with audio file
            episode_dir = os.path.join(temp_dir, 'test-episode')
            os.makedirs(episode_dir)
            
            with open(os.path.join(episode_dir, 'audio.mp3'), 'w') as f:
                f.write('audio content')
            with open(os.path.join(episode_dir, 'readme.txt'), 'w') as f:
                f.write('readme content')
            
            # Track metadata passed to upload_with_retry
            uploaded_metadata = {}
            
            def mock_upload_with_retry(local_file, s3_key, metadata=None):
                filename = os.path.basename(local_file)
                uploaded_metadata[filename] = metadata
                return {
                    'success': True,
                    'bucket': 'test-bucket',
                    's3_key': s3_key,
                    'file_size': 1000,
                    'upload_duration': 0.5,
                    'attempts': 1,
                    'url': f'https://test-bucket.s3.amazonaws.com/{s3_key}'
                }
            
            uploader.upload_with_retry = mock_upload_with_retry
            
            # Test upload with metadata
            episode_metadata = {
                'title': 'Test Episode',
                'duration': '300',
                'guid': 'test-guid'
            }
            
            uploader.upload_episode_directory(
                episode_dir=episode_dir,
                base_s3_path='podcast/2025/test-episode',
                episode_metadata=episode_metadata
            )
            
            # Verify metadata was applied to audio file
            assert 'audio.mp3' in uploaded_metadata
            audio_metadata = uploaded_metadata['audio.mp3']
            assert audio_metadata is not None
            assert audio_metadata['title'] == 'Test Episode'
            assert audio_metadata['duration'] == '300'
            assert audio_metadata['guid'] == 'test-guid'
            
            # Verify metadata was NOT applied to non-audio file
            assert 'readme.txt' in uploaded_metadata
            readme_metadata = uploaded_metadata['readme.txt']
            assert readme_metadata is None
    
    def test_upload_episode_directory_file_type_detection(self, uploader):
        """Test that different file types are correctly categorized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory with various file types
            episode_dir = os.path.join(temp_dir, 'test-episode')
            os.makedirs(episode_dir)
            
            # Create files of different types
            test_files = [
                ('episode.mp3', 'audio'),      # Audio file
                ('episode.wav', 'audio'),      # Another audio file
                ('cover.jpg', 'image'),        # Image file
                ('thumb.png', 'image'),        # Another image file
                ('data.json', 'other'),        # Other file
                ('readme.txt', 'other')        # Other file
            ]
            
            for filename, _ in test_files:
                with open(os.path.join(episode_dir, filename), 'w') as f:
                    f.write('content')
            
            # Mock successful upload for all files
            def mock_upload_with_retry(local_file, s3_key, metadata=None):
                return {
                    'success': True,
                    'bucket': 'test-bucket',
                    's3_key': s3_key,
                    'file_size': 1000,
                    'upload_duration': 0.5,
                    'attempts': 1,
                    'url': f'https://test-bucket.s3.amazonaws.com/{s3_key}'
                }
            
            uploader.upload_with_retry = mock_upload_with_retry
            
            # Test upload
            result = uploader.upload_episode_directory(
                episode_dir=episode_dir,
                base_s3_path='podcast/2025/test-episode'
            )
            
            # Verify audio file detection (should pick first audio file)
            assert result['audio_file'] is not None
            assert result['audio_file']['filename'] in ['episode.mp3', 'episode.wav']
            
            # Verify image file detection (should pick first image file)
            assert result['episode_image'] is not None
            assert result['episode_image']['filename'] in ['cover.jpg', 'thumb.png']
            
            # Verify all files were uploaded
            assert result['total_files'] == 6
            assert result['failed_files'] == 0