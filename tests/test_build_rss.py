"""
Tests for RSS generation script (build_rss.py).

This module tests the RSS feed generation functionality including:
- Episode metadata handling
- RSS XML generation
- S3 integration
- Atomic deployment
- Error handling and retry logic
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from build_rss import EpisodeMetadata, RSSGenerator, StructuredLogger


class TestEpisodeMetadata:
    """Test cases for EpisodeMetadata class."""
    
    def test_episode_metadata_creation(self, sample_episode_metadata):
        """Test creating EpisodeMetadata from dictionary."""
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        assert episode.slug == "20250618-test-episode"
        assert episode.title == "Test Episode"
        assert episode.description == "This is a test episode description"
        assert episode.duration_seconds == 1800
        assert episode.file_size_bytes == 25000000
        assert episode.mp3_url == "https://cdn.example.com/podcast/2025/20250618-test-episode.mp3"
        assert episode.guid == "repo-abc1234-20250618-test-episode"
        assert episode.spotify_url is None
    
    def test_episode_metadata_to_dict(self, sample_episode_metadata):
        """Test converting EpisodeMetadata to dictionary."""
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        result_dict = episode.to_dict()
        
        assert result_dict['slug'] == episode.slug
        assert result_dict['title'] == episode.title
        assert result_dict['description'] == episode.description
        assert result_dict['duration_seconds'] == episode.duration_seconds
        assert result_dict['file_size_bytes'] == episode.file_size_bytes
        assert result_dict['mp3_url'] == episode.mp3_url
        assert result_dict['guid'] == episode.guid
    
    def test_episode_metadata_with_spotify_url(self, sample_episode_metadata):
        """Test EpisodeMetadata with Spotify URL."""
        sample_episode_metadata['spotify_url'] = 'https://open.spotify.com/episode/test123'
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        assert episode.spotify_url == 'https://open.spotify.com/episode/test123'
    
    def test_episode_metadata_date_parsing(self, sample_episode_metadata):
        """Test date parsing in EpisodeMetadata."""
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        assert isinstance(episode.pub_date, datetime)
        assert episode.pub_date.tzinfo is not None
        assert episode.pub_date.year == 2025
        assert episode.pub_date.month == 6
        assert episode.pub_date.day == 18


class TestStructuredLogger:
    """Test cases for StructuredLogger class."""
    
    def test_logger_creation(self):
        """Test creating StructuredLogger."""
        logger = StructuredLogger("test_logger")
        assert logger.logger.name == "test_logger"
    
    @patch('build_rss.logging.getLogger')
    def test_log_event(self, mock_get_logger):
        """Test structured event logging."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        logger = StructuredLogger("test")
        logger.log_event("test_event", key1="value1", key2="value2")
        
        # Verify info was called
        mock_logger.info.assert_called_once()
        
        # Parse the logged JSON
        logged_json = mock_logger.info.call_args[0][0]
        logged_data = json.loads(logged_json)
        
        assert logged_data['event_type'] == "test_event"
        assert logged_data['key1'] == "value1"
        assert logged_data['key2'] == "value2"
        assert 'timestamp' in logged_data


class TestRSSGenerator:
    """Test cases for RSSGenerator class."""
    
    @pytest.fixture
    def rss_generator(self, mock_s3_client, mock_environment_variables):
        """Create RSSGenerator instance for testing."""
        return RSSGenerator(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            base_url="https://cdn.test.com"
        )
    
    def test_rss_generator_initialization(self, mock_s3_client, mock_environment_variables):
        """Test RSSGenerator initialization."""
        generator = RSSGenerator(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            base_url="https://cdn.test.com/"
        )
        
        assert generator.s3_client == mock_s3_client
        assert generator.bucket_name == "test-bucket"
        assert generator.base_url == "https://cdn.test.com"  # Should strip trailing slash
        assert generator.podcast_config['title'] == 'Test Podcast'
    
    def test_parse_date_from_slug(self, rss_generator):
        """Test date parsing from episode slug."""
        # Test valid date
        date = rss_generator._parse_date_from_slug("20250618-test-episode")
        assert date.year == 2025
        assert date.month == 6
        assert date.day == 18
        assert date.tzinfo == timezone.utc
        
        # Test invalid date - should fallback to current date
        date = rss_generator._parse_date_from_slug("invalid-slug")
        assert isinstance(date, datetime)
        assert date.tzinfo == timezone.utc
    
    def test_seconds_to_duration(self, rss_generator):
        """Test duration conversion."""
        assert rss_generator._seconds_to_duration(0) == "00:00:00"
        assert rss_generator._seconds_to_duration(30) == "00:00:30"
        assert rss_generator._seconds_to_duration(90) == "00:01:30"
        assert rss_generator._seconds_to_duration(3661) == "01:01:01"
        assert rss_generator._seconds_to_duration(-1) == "00:00:00"
    
    @patch('build_rss.datetime')
    def test_collect_existing_episodes(self, mock_datetime, rss_generator):
        """Test collecting existing episodes from S3."""
        # Mock datetime.now for consistent testing
        mock_datetime.now.return_value = datetime(2025, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.utcnow.return_value = datetime(2025, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.strptime.side_effect = datetime.strptime
        
        episodes = rss_generator.collect_existing_episodes()
        
        assert len(episodes) == 1
        episode = episodes[0]
        assert episode.slug == "20250618-test-episode"
        assert episode.title == "Test Episode"
        assert episode.file_size_bytes == 25000000
        assert episode.mp3_url == "https://cdn.test.com/podcast/2025/20250618-test-episode.mp3"
        
        # Verify S3 calls
        rss_generator.s3_client.get_paginator.assert_called_once_with('list_objects_v2')
        rss_generator.s3_client.head_object.assert_called_once()
    
    def test_collect_existing_episodes_error_handling(self, rss_generator):
        """Test error handling in collect_existing_episodes."""
        # Mock S3 client to raise an error
        rss_generator.s3_client.get_paginator.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchBucket'}},
            operation_name='ListObjectsV2'
        )
        
        with pytest.raises(ClientError):
            rss_generator.collect_existing_episodes()
    
    def test_generate_rss_with_episodes(self, rss_generator, sample_episode_metadata):
        """Test RSS generation with episodes."""
        episodes = [EpisodeMetadata.from_dict(sample_episode_metadata)]
        
        rss_xml = rss_generator.generate_rss(episodes)
        
        assert '<?xml version=' in rss_xml and 'encoding=' in rss_xml
        assert '<rss' in rss_xml and 'version="2.0"' in rss_xml
        assert '<title>Test Podcast</title>' in rss_xml
        assert '<title>Test Episode</title>' in rss_xml
        assert 'repo-abc1234-20250618-test-episode' in rss_xml
        assert 'https://cdn.example.com/podcast/2025/20250618-test-episode.mp3' in rss_xml
        assert '<enclosure' in rss_xml
        assert 'audio/mpeg' in rss_xml
    
    def test_generate_rss_with_new_episode(self, rss_generator, sample_episode_metadata):
        """Test RSS generation with new episode added."""
        existing_episodes = []
        new_episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        rss_xml = rss_generator.generate_rss(existing_episodes, new_episode)
        
        assert 'Test Episode' in rss_xml
        assert 'repo-abc1234-20250618-test-episode' in rss_xml
    
    def test_generate_rss_duplicate_guid_handling(self, rss_generator, sample_episode_metadata):
        """Test RSS generation handles duplicate GUIDs."""
        existing_episodes = [EpisodeMetadata.from_dict(sample_episode_metadata)]
        new_episode = EpisodeMetadata.from_dict(sample_episode_metadata)  # Same GUID
        
        rss_xml = rss_generator.generate_rss(existing_episodes, new_episode)
        
        # Should only contain one episode with this GUID
        guid_count = rss_xml.count('repo-abc1234-20250618-test-episode')
        assert guid_count == 1  # Should appear only once in the RSS
    
    def test_deploy_rss_atomic_success(self, rss_generator):
        """Test successful atomic RSS deployment."""
        rss_content = '<rss>test content</rss>'
        
        result_url = rss_generator.deploy_rss_atomic(rss_content)
        
        assert result_url == "https://cdn.test.com/rss.xml"
        
        # Verify S3 operations were called
        rss_generator.s3_client.put_object.assert_called_once()
        rss_generator.s3_client.copy_object.assert_called_once()
        rss_generator.s3_client.delete_object.assert_called_once()
        rss_generator.s3_client.head_object.assert_called_once()
        
        # Verify put_object call arguments
        put_call_args = rss_generator.s3_client.put_object.call_args
        assert put_call_args[1]['Key'] == 'rss.xml.new'
        assert put_call_args[1]['ContentType'] == 'application/rss+xml; charset=utf-8'
        assert put_call_args[1]['CacheControl'] == 'public, max-age=300'
        assert put_call_args[1]['ACL'] == 'public-read'
    
    def test_deploy_rss_atomic_failure_cleanup(self, rss_generator):
        """Test atomic deployment failure and cleanup."""
        rss_content = '<rss>test content</rss>'
        
        # Mock put_object to fail
        rss_generator.s3_client.put_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name='PutObject'
        )
        
        with pytest.raises(ClientError):
            rss_generator.deploy_rss_atomic(rss_content)
        
        # Verify cleanup was attempted
        rss_generator.s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="rss.xml.new"
        )
    
    def test_update_episode_metadata(self, rss_generator, sample_episode_metadata):
        """Test updating episode metadata in S3."""
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        episode.spotify_url = 'https://open.spotify.com/episode/test123'
        
        rss_generator.update_episode_metadata(episode)
        
        # Verify S3 operations
        rss_generator.s3_client.head_object.assert_called_once()
        rss_generator.s3_client.copy_object.assert_called_once()
        
        # Verify copy_object call
        copy_call_args = rss_generator.s3_client.copy_object.call_args
        metadata = copy_call_args[1]['Metadata']
        assert metadata['title'] == episode.title
        assert metadata['description'] == episode.description
        assert metadata['duration'] == str(episode.duration_seconds)
        assert metadata['guid'] == episode.guid
        assert metadata['spotify_url'] == episode.spotify_url
    
    def test_update_episode_metadata_error_handling(self, rss_generator, sample_episode_metadata):
        """Test error handling in update_episode_metadata."""
        episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        # Mock head_object to fail
        rss_generator.s3_client.head_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchKey'}},
            operation_name='HeadObject'
        )
        
        # Should not raise exception, just log error
        rss_generator.update_episode_metadata(episode)


class TestMainFunction:
    """Test cases for main function."""
    
    @patch('build_rss.boto3.client')
    @patch('build_rss.sys.argv')
    def test_main_with_valid_args(self, mock_argv, mock_boto3, mock_s3_client, 
                                  sample_episode_metadata, mock_environment_variables):
        """Test main function with valid arguments."""
        mock_argv.__getitem__.side_effect = [
            'build_rss.py',
            '--bucket', 'test-bucket',
            '--base-url', 'https://cdn.test.com',
            '--episode-metadata', json.dumps(sample_episode_metadata),
            '--commit-sha', 'abc1234'
        ]
        mock_boto3.return_value = mock_s3_client
        
        with patch('build_rss.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                bucket='test-bucket',
                base_url='https://cdn.test.com',
                episode_metadata=json.dumps(sample_episode_metadata),
                commit_sha='abc1234'
            )
            
            with patch('build_rss.print') as mock_print:
                from build_rss import main
                main()
                
                # Verify GitHub Actions outputs were printed
                assert any('::set-output name=rss-url::' in str(call) for call in mock_print.call_args_list)
    
    @patch('build_rss.boto3.client')
    def test_main_with_credentials_error(self, mock_boto3):
        """Test main function with AWS credentials error."""
        from botocore.exceptions import NoCredentialsError
        mock_boto3.side_effect = NoCredentialsError()
        
        with patch('build_rss.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                bucket='test-bucket',
                base_url='https://cdn.test.com',
                episode_metadata=None,
                commit_sha='abc1234'
            )
            
            with patch('build_rss.sys.exit') as mock_exit:
                from build_rss import main
                main()
                mock_exit.assert_called_with(1)
    
    @patch('build_rss.boto3.client')
    def test_main_with_invalid_metadata(self, mock_boto3, mock_s3_client):
        """Test main function with invalid episode metadata."""
        mock_boto3.return_value = mock_s3_client
        
        with patch('build_rss.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                bucket='test-bucket',
                base_url='https://cdn.test.com',
                episode_metadata='invalid json',
                commit_sha='abc1234'
            )
            
            with patch('build_rss.sys.exit') as mock_exit:
                from build_rss import main
                main()
                mock_exit.assert_called_with(1)


class TestIntegration:
    """Integration tests for RSS generation."""
    
    @pytest.mark.integration
    def test_end_to_end_rss_generation(self, mock_s3_client, sample_episode_metadata, 
                                      mock_environment_variables):
        """Test complete RSS generation workflow."""
        generator = RSSGenerator(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            base_url="https://cdn.test.com"
        )
        
        # Collect existing episodes
        existing_episodes = generator.collect_existing_episodes()
        
        # Add new episode
        new_episode = EpisodeMetadata.from_dict(sample_episode_metadata)
        
        # Generate RSS
        rss_xml = generator.generate_rss(existing_episodes, new_episode)
        
        # Deploy RSS
        rss_url = generator.deploy_rss_atomic(rss_xml)
        
        # Update episode metadata
        generator.update_episode_metadata(new_episode)
        
        # Verify results
        assert rss_url == "https://cdn.test.com/rss.xml"
        assert 'Test Episode' in rss_xml
        assert new_episode.guid in rss_xml
    
    @pytest.mark.slow
    def test_large_episode_list_performance(self, mock_s3_client, mock_environment_variables):
        """Test RSS generation performance with large episode list."""
        generator = RSSGenerator(
            s3_client=mock_s3_client,
            bucket_name="test-bucket", 
            base_url="https://cdn.test.com"
        )
        
        # Create large episode list
        episodes = []
        for i in range(100):
            episode_data = {
                "slug": f"202506{i:02d}-episode-{i}",
                "title": f"Episode {i}",
                "description": f"Description for episode {i}",
                "pub_date": f"2025-06-{i%28+1:02d}T10:00:00+00:00",
                "duration_seconds": 1800,
                "file_size_bytes": 25000000,
                "mp3_url": f"https://cdn.test.com/podcast/2025/202506{i:02d}-episode-{i}.mp3",
                "guid": f"repo-abc123-202506{i:02d}-episode-{i}",
                "s3_key": f"podcast/2025/202506{i:02d}-episode-{i}.mp3",
                "year": 2025
            }
            episodes.append(EpisodeMetadata.from_dict(episode_data))
        
        # Generate RSS (should complete quickly)
        import time
        start_time = time.time()
        rss_xml = generator.generate_rss(episodes)
        end_time = time.time()
        
        # Should complete within reasonable time (less than 5 seconds)
        assert end_time - start_time < 5.0
        assert len(episodes) == 100
        assert 'Episode 0' in rss_xml
        assert 'Episode 99' in rss_xml