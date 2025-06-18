"""
Integration Tests for Episode Directory Workflow

This module tests the complete episode directory workflow including:
- Episode directory structure setup
- Metadata extraction from episode directories
- S3 upload with directory structure
- RSS generation with iTunes fields
- End-to-end integration scenarios
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from extract_metadata import MetadataExtractor
from upload_s3 import S3Uploader
from build_rss import RSSGenerator, EpisodeMetadata


class TestEpisodeDirectoryIntegration:
    """Integration tests for episode directory workflow."""
    
    @pytest.fixture
    def sample_episode_directory(self):
        """Create a sample episode directory with files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-integration-test')
            os.makedirs(episode_dir)
            
            # Create audio file
            audio_file = os.path.join(episode_dir, 'episode.mp3')
            with open(audio_file, 'wb') as f:
                # Write minimal MP3 header
                f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')
                f.write(b'\x00' * 5000)  # Dummy audio data
            
            # Create episode image
            image_file = os.path.join(episode_dir, 'cover.jpg')
            with open(image_file, 'wb') as f:
                f.write(b'\xff\xd8\xff\xe0')  # JPEG header
                f.write(b'\x00' * 1000)  # Dummy image data
            
            # Create episode_data.json
            episode_data = {
                'title': 'Integration Test Episode',
                'description': 'This is a comprehensive integration test episode with rich metadata',
                'season': 2,
                'episode_number': 15,
                'episode_type': 'full',
                'itunes_summary': 'Detailed summary for iTunes with rich HTML content',
                'itunes_subtitle': 'Short subtitle for iTunes',
                'itunes_keywords': ['integration', 'test', 'automation', 'podcast'],
                'itunes_explicit': 'no',
                'episode_image': 'cover.jpg'
            }
            
            json_file = os.path.join(episode_dir, 'episode_data.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(episode_data, f, indent=2, ensure_ascii=False)
            
            yield episode_dir
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client for testing."""
        mock_client = Mock()
        mock_client.head_bucket = Mock()
        mock_client.upload_file = Mock()
        mock_client.put_object = Mock()
        mock_client.copy_object = Mock()
        mock_client.delete_object = Mock()
        mock_client.head_object = Mock(return_value={
            'ContentLength': 5000,
            'LastModified': datetime.now(timezone.utc),
            'Metadata': {}
        })
        return mock_client
    
    def test_metadata_extraction_from_directory(self, sample_episode_directory):
        """Test metadata extraction from episode directory."""
        extractor = MetadataExtractor('https://cdn.test.com', 'integration123')
        
        with patch('mutagen.File') as mock_mutagen:
            # Mock audio file metadata
            mock_audio = Mock()
            mock_audio.info.length = 1800  # 30 minutes
            mock_mutagen.return_value = mock_audio
            
            metadata = extractor.extract_from_directory(sample_episode_directory)
            
            # Verify basic metadata
            assert metadata['slug'] == '20250618-integration-test'
            assert metadata['title'] == 'Integration Test Episode'
            assert metadata['description'] == 'This is a comprehensive integration test episode with rich metadata'
            assert metadata['duration_seconds'] == 1800
            assert metadata['file_extension'] == '.mp3'
            
            # Verify iTunes fields
            assert metadata['season'] == 2
            assert metadata['episode_number'] == 15
            assert metadata['episode_type'] == 'full'
            assert metadata['itunes_summary'] == 'Detailed summary for iTunes with rich HTML content'
            assert metadata['itunes_subtitle'] == 'Short subtitle for iTunes'
            assert metadata['itunes_keywords'] == ['integration', 'test', 'automation', 'podcast']
            assert metadata['itunes_explicit'] == 'no'
            assert metadata['episode_image_url'] == 'https://cdn.test.com/podcast/2025/20250618-integration-test/cover.jpg'
            
            # Verify S3 paths
            assert metadata['s3_base_path'] == 'podcast/2025/20250618-integration-test'
            assert metadata['audio_url'] == 'https://cdn.test.com/podcast/2025/20250618-integration-test/episode.mp3'
            assert metadata['guid'] == 'repo-integra-20250618-integration-test'
    
    def test_s3_upload_episode_directory(self, sample_episode_directory, mock_s3_client):
        """Test S3 upload of entire episode directory."""
        uploader = S3Uploader.__new__(S3Uploader)
        uploader.bucket_name = 'test-bucket'
        uploader.s3_client = mock_s3_client
        
        # Mock successful uploads
        def mock_upload_with_retry(local_file, s3_key, metadata=None):
            filename = os.path.basename(local_file)
            return {
                'success': True,
                'bucket': 'test-bucket',
                's3_key': s3_key,
                'file_size': 5000,
                'upload_duration': 0.5,
                'attempts': 1,
                'url': f'https://test-bucket.s3.amazonaws.com/{s3_key}'
            }
        
        uploader.upload_with_retry = mock_upload_with_retry
        
        episode_metadata = {
            'title': 'Integration Test Episode',
            'description': 'Test episode description',
            'duration': '1800',
            'guid': 'test-guid-integration'
        }
        
        result = uploader.upload_episode_directory(
            episode_dir=sample_episode_directory,
            base_s3_path='podcast/2025/20250618-integration-test',
            episode_metadata=episode_metadata
        )
        
        # Verify upload results
        assert result['success'] is True
        assert result['total_files'] == 3  # audio, image, json
        assert result['failed_files'] == 0
        
        # Verify audio file tracking
        assert result['audio_file'] is not None
        assert result['audio_file']['filename'] == 'episode.mp3'
        assert result['audio_file']['s3_key'] == 'podcast/2025/20250618-integration-test/episode.mp3'
        
        # Verify episode image tracking
        assert result['episode_image'] is not None
        assert result['episode_image']['filename'] == 'cover.jpg'
        assert result['episode_image']['s3_key'] == 'podcast/2025/20250618-integration-test/cover.jpg'
    
    def test_rss_generation_with_directory_episodes(self, mock_s3_client):
        """Test RSS generation using episode directory data."""
        with patch.dict(os.environ, {
            'PODCAST_TITLE': 'Integration Test Podcast',
            'PODCAST_DESCRIPTION': 'Test podcast for integration testing',
            'PODCAST_AUTHOR': 'Test Author',
            'PODCAST_EMAIL': 'test@example.com'
        }):
            generator = RSSGenerator(mock_s3_client, 'test-bucket', 'https://cdn.test.com')
            
            # Create episode with full iTunes metadata
            episode = EpisodeMetadata(
                slug='20250618-integration-test',
                title='Integration Test Episode',
                description='This is a comprehensive integration test episode',
                pub_date=datetime(2025, 6, 18, tzinfo=timezone.utc),
                duration_seconds=1800,
                file_size_bytes=5000000,
                audio_url='https://cdn.test.com/podcast/2025/20250618-integration-test/episode.mp3',
                guid='repo-integration123-20250618-integration-test',
                # iTunes fields
                episode_image_url='https://cdn.test.com/podcast/2025/20250618-integration-test/cover.jpg',
                season=2,
                episode_number=15,
                episode_type='full',
                itunes_summary='Detailed summary for iTunes',
                itunes_subtitle='Short subtitle',
                itunes_keywords=['integration', 'test', 'automation'],
                itunes_explicit='no'
            )
            
            rss_xml = generator.generate_rss([episode])
            
            # Verify RSS contains basic episode info
            assert 'Integration Test Episode' in rss_xml
            assert 'repo-integration123-20250618-integration-test' in rss_xml
            assert 'https://cdn.test.com/podcast/2025/20250618-integration-test/episode.mp3' in rss_xml
            
            # Verify iTunes extensions
            assert 'itunes:season>2</itunes:season>' in rss_xml
            assert 'itunes:episode>15</itunes:episode>' in rss_xml
            # Note: episodeType='full' is the default and not explicitly added to RSS
            assert 'itunes:subtitle>Short subtitle</itunes:subtitle>' in rss_xml
            assert 'itunes:summary>Detailed summary for iTunes</itunes:summary>' in rss_xml
            assert 'itunes:explicit>no</itunes:explicit>' in rss_xml
            assert 'itunes:image href="https://cdn.test.com/podcast/2025/20250618-integration-test/cover.jpg"' in rss_xml
            assert 'itunes:keywords>integration,test,automation</itunes:keywords>' in rss_xml
            
            # Verify enclosure with correct MIME type
            assert 'enclosure' in rss_xml
            assert 'audio/mpeg' in rss_xml
    
    @pytest.mark.integration
    def test_complete_episode_directory_workflow(self, sample_episode_directory, mock_s3_client):
        """Test the complete workflow from episode directory to RSS generation."""
        base_url = 'https://cdn.integration.test'
        commit_sha = 'workflow123'
        
        # Step 1: Extract metadata from episode directory
        extractor = MetadataExtractor(base_url, commit_sha)
        
        with patch('mutagen.File') as mock_mutagen:
            mock_audio = Mock()
            mock_audio.info.length = 1800
            mock_mutagen.return_value = mock_audio
            
            metadata = extractor.extract_from_directory(sample_episode_directory)
        
        # Step 2: Upload episode directory to S3
        uploader = S3Uploader.__new__(S3Uploader)
        uploader.bucket_name = 'integration-test-bucket'
        uploader.s3_client = mock_s3_client
        
        def mock_upload_with_retry(local_file, s3_key, metadata=None):
            return {
                'success': True,
                'bucket': 'integration-test-bucket',
                's3_key': s3_key,
                'file_size': 5000,
                'upload_duration': 0.5,
                'attempts': 1,
                'url': f'https://integration-test-bucket.s3.amazonaws.com/{s3_key}'
            }
        
        uploader.upload_with_retry = mock_upload_with_retry
        
        upload_result = uploader.upload_episode_directory(
            episode_dir=sample_episode_directory,
            base_s3_path=metadata['s3_base_path'],
            episode_metadata=metadata
        )
        
        # Step 3: Create EpisodeMetadata object for RSS
        episode = EpisodeMetadata.from_dict(metadata)
        
        # Step 4: Generate RSS with iTunes extensions
        with patch.dict(os.environ, {
            'PODCAST_TITLE': 'Workflow Integration Test',
            'PODCAST_DESCRIPTION': 'Testing complete workflow',
            'PODCAST_AUTHOR': 'Integration Tester',
            'PODCAST_EMAIL': 'integration@test.com'
        }):
            generator = RSSGenerator(mock_s3_client, 'integration-test-bucket', base_url)
            rss_xml = generator.generate_rss([episode])
        
        # Step 5: Deploy RSS (mock)
        mock_s3_client.reset_mock()
        rss_url = generator.deploy_rss_atomic(rss_xml)
        
        # Verify complete workflow success
        assert upload_result['success'] is True
        assert upload_result['total_files'] == 3
        assert rss_url == f'{base_url}/rss.xml'
        
        # Verify RSS contains all expected elements
        assert 'Integration Test Episode' in rss_xml
        assert 'itunes:season>2</itunes:season>' in rss_xml
        assert 'itunes:keywords>integration,test,automation,podcast</itunes:keywords>' in rss_xml
        assert metadata['episode_image_url'] in rss_xml
        
        # Verify S3 operations were called correctly
        assert mock_s3_client.put_object.called
        assert mock_s3_client.copy_object.called
        assert mock_s3_client.delete_object.called
    
    def test_backward_compatibility_with_legacy_episodes(self, mock_s3_client):
        """Test that directory-based episodes work alongside legacy S3-based episodes."""
        with patch.dict(os.environ, {
            'PODCAST_TITLE': 'Compatibility Test Podcast',
            'PODCAST_DESCRIPTION': 'Testing backward compatibility',
            'PODCAST_AUTHOR': 'Test Author',
            'PODCAST_EMAIL': 'test@example.com'
        }):
            generator = RSSGenerator(mock_s3_client, 'test-bucket', 'https://cdn.test.com')
            
            # Create legacy episode (S3-based, no iTunes fields)
            legacy_episode = EpisodeMetadata(
                slug='20250617-legacy-episode',
                title='Legacy Episode',
                description='Legacy episode without iTunes fields',
                pub_date=datetime(2025, 6, 17, tzinfo=timezone.utc),
                duration_seconds=1200,
                file_size_bytes=3000000,
                audio_url='https://cdn.test.com/podcast/2025/20250617-legacy-episode.mp3',
                guid='repo-legacy123-20250617-legacy-episode'
            )
            
            # Create new directory-based episode (with iTunes fields)
            directory_episode = EpisodeMetadata(
                slug='20250618-directory-episode',
                title='Directory Episode',
                description='Episode from directory structure with iTunes fields',
                pub_date=datetime(2025, 6, 18, tzinfo=timezone.utc),
                duration_seconds=1800,
                file_size_bytes=5000000,
                audio_url='https://cdn.test.com/podcast/2025/20250618-directory-episode/episode.mp3',
                guid='repo-directory123-20250618-directory-episode',
                # iTunes fields
                episode_image_url='https://cdn.test.com/podcast/2025/20250618-directory-episode/cover.jpg',
                season=1,
                episode_number=2,
                itunes_keywords=['directory', 'new-format']
            )
            
            # Generate RSS with both episode types
            episodes = [directory_episode, legacy_episode]  # Newer first
            rss_xml = generator.generate_rss(episodes)
            
            # Verify both episodes are included
            assert 'Legacy Episode' in rss_xml
            assert 'Directory Episode' in rss_xml
            
            # Verify legacy episode doesn't break RSS
            assert 'repo-legacy123-20250617-legacy-episode' in rss_xml
            assert 'repo-directory123-20250618-directory-episode' in rss_xml
            
            # Verify iTunes fields only appear for directory episode
            assert 'itunes:season>1</itunes:season>' in rss_xml  # Only for directory episode
            assert 'itunes:keywords>directory,new-format</itunes:keywords>' in rss_xml
            
            # Verify both episodes have proper enclosures
            assert rss_xml.count('<enclosure') == 2
            assert 'audio/mpeg' in rss_xml
    
    def test_error_handling_in_integration_workflow(self, sample_episode_directory):
        """Test error handling throughout the integration workflow."""
        extractor = MetadataExtractor('https://cdn.test.com', 'error123')
        
        # Test metadata extraction with invalid directory
        with pytest.raises(FileNotFoundError):
            extractor.extract_from_directory('/nonexistent/directory')
        
        # Test metadata extraction with valid directory but corrupted JSON
        corrupted_dir = os.path.join(os.path.dirname(sample_episode_directory), '20250618-corrupted-test')
        os.makedirs(corrupted_dir, exist_ok=True)
        
        # Create audio file
        audio_file = os.path.join(corrupted_dir, 'audio.mp3')
        with open(audio_file, 'w') as f:
            f.write('dummy audio')
        
        # Create corrupted JSON
        json_file = os.path.join(corrupted_dir, 'episode_data.json')
        with open(json_file, 'w') as f:
            f.write('{ invalid json }')
        
        # Should handle corrupted JSON gracefully
        with patch('mutagen.File'):
            metadata = extractor.extract_from_directory(corrupted_dir)
            assert metadata['title'] == 'Corrupted Test'  # Fallback from slug
        
        # Cleanup
        import shutil
        if os.path.exists(corrupted_dir):
            shutil.rmtree(corrupted_dir)
    
    def test_performance_with_multiple_directories(self, mock_s3_client):
        """Test performance with multiple episode directories."""
        episodes = []
        
        # Create multiple episodes with varying complexity
        for i in range(10):
            episode = EpisodeMetadata(
                slug=f'202506{i:02d}-performance-test-{i}',
                title=f'Performance Test Episode {i}',
                description=f'Performance test episode number {i} with varying metadata',
                pub_date=datetime(2025, 6, i+1, tzinfo=timezone.utc),
                duration_seconds=1800 + i * 60,
                file_size_bytes=5000000 + i * 100000,
                audio_url=f'https://cdn.test.com/podcast/2025/202506{i:02d}-performance-test-{i}/episode.mp3',
                guid=f'repo-perf123-202506{i:02d}-performance-test-{i}',
                # Alternate iTunes fields for complexity
                season=1 if i % 2 == 0 else 2,
                episode_number=i + 1,
                episode_type='full' if i % 3 != 0 else 'bonus',
                itunes_keywords=[f'performance', f'test-{i}', f'episode-{i}'] if i % 2 == 0 else None,
                episode_image_url=f'https://cdn.test.com/podcast/2025/202506{i:02d}-performance-test-{i}/cover.jpg' if i % 3 == 0 else None
            )
            episodes.append(episode)
        
        # Test RSS generation performance
        with patch.dict(os.environ, {
            'PODCAST_TITLE': 'Performance Test Podcast',
            'PODCAST_DESCRIPTION': 'Testing RSS generation performance',
            'PODCAST_AUTHOR': 'Performance Tester',
            'PODCAST_EMAIL': 'perf@test.com'
        }):
            generator = RSSGenerator(mock_s3_client, 'perf-test-bucket', 'https://cdn.test.com')
            
            import time
            start_time = time.time()
            rss_xml = generator.generate_rss(episodes)
            end_time = time.time()
            
            # Should complete quickly (under 2 seconds)
            assert end_time - start_time < 2.0
            
            # Verify all episodes are included
            for i in range(10):
                assert f'Performance Test Episode {i}' in rss_xml
                assert f'repo-perf123-202506{i:02d}-performance-test-{i}' in rss_xml
            
            # Verify iTunes fields are properly included/excluded
            assert rss_xml.count('itunes:season>1</itunes:season>') == 5  # Even numbered episodes
            assert rss_xml.count('itunes:season>2</itunes:season>') == 5  # Odd numbered episodes
            assert 'itunes:keywords>performance,test-0,episode-0</itunes:keywords>' in rss_xml