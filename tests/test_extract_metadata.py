"""
Tests for metadata extraction script (extract_metadata.py).

This module tests the audio metadata extraction functionality including:
- Audio file parsing (MP3/WAV)
- ID3 tag extraction
- Slug format validation
- Metadata structure generation
- Error handling and fallbacks
"""

import os
import json
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from extract_metadata import MetadataExtractor


class TestMetadataExtractor:
    """Test cases for MetadataExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        """Create MetadataExtractor instance for testing."""
        return MetadataExtractor(
            base_url="https://cdn.test.com",
            commit_sha="abc1234567890"
        )
    
    def test_extractor_initialization(self):
        """Test MetadataExtractor initialization."""
        extractor = MetadataExtractor(
            base_url="https://cdn.test.com/",
            commit_sha="abc1234567890"
        )
        
        assert extractor.base_url == "https://cdn.test.com"  # Should strip trailing slash
        assert extractor.commit_sha == "abc1234567890"
    
    def test_validate_slug_format_valid(self, extractor):
        """Test slug format validation with valid slugs."""
        valid_slugs = [
            "20250618-test-episode",
            "20250101-new-year-special",
            "20251231-year-end-review",
            "20250630-episode-100-celebration",
            "20250215-tech-talk-with-experts"
        ]
        
        for slug in valid_slugs:
            assert extractor._validate_slug_format(slug), f"Should be valid: {slug}"
    
    def test_validate_slug_format_invalid(self, extractor):
        """Test slug format validation with invalid slugs."""
        invalid_slugs = [
            "invalid-slug",  # No date
            "2025-06-18-episode",  # Wrong date format
            "20250618",  # No title part
            "20250618-",  # Empty title
            "20250632-invalid-date",  # Invalid date
            "20250618-UPPERCASE",  # Uppercase letters
            "20250618-with_underscore",  # Underscore not allowed
            "20250618--double-dash",  # Double dash
            "20250618-title-",  # Ends with dash
            "20250618-title with spaces",  # Spaces not allowed
            "",  # Empty string
            "short"  # Too short
        ]
        
        for slug in invalid_slugs:
            assert not extractor._validate_slug_format(slug), f"Should be invalid: {slug}"
    
    def test_generate_title_from_slug(self, extractor):
        """Test title generation from slug."""
        test_cases = [
            ("20250618-test-episode", "Test Episode"),
            ("20250101-new-year-special", "New Year Special"),
            ("20251231-tech-talk-with-experts", "Tech Talk With Experts"),
            ("20250630-episode-100", "Episode 100"),
            ("20250215-single-word", "Single Word")
        ]
        
        for slug, expected_title in test_cases:
            result = extractor._generate_title_from_slug(slug)
            assert result == expected_title, f"Slug: {slug}, Expected: {expected_title}, Got: {result}"
    
    def test_extract_title_from_audio_file(self, extractor, mock_mutagen_file):
        """Test title extraction from audio file tags."""
        # Test with TIT2 tag
        result = extractor._extract_title(mock_mutagen_file, "20250618-fallback")
        assert result == "Test Episode Title"
        
        # Test with no tags - should use fallback
        mock_mutagen_file.tags = None
        result = extractor._extract_title(mock_mutagen_file, "20250618-fallback-title")
        assert result == "Fallback Title"
        
        # Test with empty tags
        mock_mutagen_file.tags = {}
        result = extractor._extract_title(mock_mutagen_file, "20250618-empty-tags")
        assert result == "Empty Tags"
    
    def test_extract_description_from_audio_file(self, extractor, mock_mutagen_file):
        """Test description extraction from audio file tags."""
        # Test with COMM tag
        result = extractor._extract_description(mock_mutagen_file, "20250618-test")
        assert result == "Test episode description"
        
        # Test with no tags - should generate from slug
        mock_mutagen_file.tags = None
        result = extractor._extract_description(mock_mutagen_file, "20250618-test-episode")
        assert result == "Episode: Test Episode"
        
        # Test with empty description tag
        mock_mutagen_file.tags = {'COMM::eng': ['']}
        result = extractor._extract_description(mock_mutagen_file, "20250618-empty-desc")
        assert result == "Episode: Empty Desc"
    
    @patch('extract_metadata.os.path.exists')
    @patch('extract_metadata.os.path.getsize')
    @patch('extract_metadata.mutagen.File')
    def test_extract_from_file_success(self, mock_mutagen, mock_getsize, mock_exists, 
                                     extractor, mock_mutagen_file):
        """Test successful metadata extraction from MP3 file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 25000000
        mock_mutagen.return_value = mock_mutagen_file
        
        mp3_path = "/test/20250618-test-episode.mp3"
        result = extractor.extract_from_file(mp3_path)
        
        # Verify basic metadata
        assert result['slug'] == "20250618-test-episode"
        assert result['title'] == "Test Episode Title"
        assert result['description'] == "Test episode description"
        assert result['duration_seconds'] == 1800
        assert result['file_size_bytes'] == 25000000
        assert result['audio_url'] == "https://cdn.test.com/podcast/2025/20250618-test-episode.mp3"
        assert result['guid'] == "repo-abc1234-20250618-test-episode"
        assert result['s3_key'] == "podcast/2025/20250618-test-episode.mp3"
        assert result['year'] == 2025
        
        # Verify date parsing
        pub_date = datetime.fromisoformat(result['pub_date'])
        assert pub_date.year == 2025
        assert pub_date.month == 6
        assert pub_date.day == 18
        assert pub_date.tzinfo == timezone.utc
    
    @patch('extract_metadata.os.path.exists')
    def test_extract_from_file_not_found(self, mock_exists, extractor):
        """Test metadata extraction with non-existent file."""
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            extractor.extract_from_file("/nonexistent/file.mp3")
    
    @patch('extract_metadata.os.path.exists')
    def test_extract_from_file_invalid_extension(self, mock_exists, extractor):
        """Test metadata extraction with invalid file extension."""
        mock_exists.return_value = True
        
        with pytest.raises(ValueError, match="File is not a supported audio format"):
            extractor.extract_from_file("/test/file.txt")
    
    @patch('extract_metadata.os.path.exists')
    @patch('extract_metadata.os.path.getsize')
    @patch('extract_metadata.mutagen.File')
    def test_extract_from_wav_file_success(self, mock_mutagen, mock_getsize, mock_exists, 
                                          extractor, mock_mutagen_file):
        """Test successful metadata extraction from WAV file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 30000000
        mock_mutagen.return_value = mock_mutagen_file
        
        wav_path = "/test/20250618-test-episode.wav"
        result = extractor.extract_from_file(wav_path)
        
        # Verify basic metadata (same as MP3 but with WAV extension)
        assert result['slug'] == "20250618-test-episode"
        assert result['audio_url'] == "https://cdn.test.com/podcast/2025/20250618-test-episode.wav"
        assert result['s3_key'] == "podcast/2025/20250618-test-episode.wav"
        assert result['file_extension'] == ".wav"
    
    @patch('extract_metadata.os.path.exists')
    def test_extract_from_file_invalid_slug(self, mock_exists, extractor):
        """Test metadata extraction with invalid slug format."""
        mock_exists.return_value = True
        
        with pytest.raises(ValueError, match="Invalid slug format"):
            extractor.extract_from_file("/test/invalid-slug-format.mp3")
    
    @patch('extract_metadata.os.path.exists')
    @patch('extract_metadata.os.path.getsize')
    @patch('extract_metadata.mutagen.File')
    def test_extract_from_file_no_id3_tags(self, mock_mutagen, mock_getsize, mock_exists, extractor):
        """Test metadata extraction with no ID3 tags (fallback behavior)."""
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 15000000
        mock_mutagen.return_value = None  # Simulate no metadata
        
        mp3_path = "/test/20250618-no-tags-episode.mp3"
        
        with patch('extract_metadata.logger') as mock_logger:
            result = extractor.extract_from_file(mp3_path)
        
        # Should use fallback values
        assert result['slug'] == "20250618-no-tags-episode"
        assert result['title'] == "No Tags Episode"
        assert result['description'] == "Episode: No Tags Episode"
        assert result['duration_seconds'] == 0  # No duration available
        assert result['file_size_bytes'] == 15000000
        assert result['guid'] == "repo-abc1234-20250618-no-tags-episode"
        
        # Should log warning about missing tags
        mock_logger.warning.assert_called_once()
    
    @patch('extract_metadata.os.path.exists')
    @patch('extract_metadata.os.path.getsize')
    @patch('extract_metadata.mutagen.File')
    def test_extract_from_file_corrupted_audio(self, mock_mutagen, mock_getsize, mock_exists, extractor):
        """Test metadata extraction with corrupted audio file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1000
        mock_mutagen.side_effect = Exception("Corrupted file")
        
        mp3_path = "/test/20250618-corrupted-file.mp3"
        
        with patch('extract_metadata.logger') as mock_logger:
            result = extractor.extract_from_file(mp3_path)
        
        # Should handle error gracefully and use fallbacks
        assert result['slug'] == "20250618-corrupted-file"
        assert result['title'] == "Corrupted File"
        assert result['duration_seconds'] == 0
        
        # Should log warning
        mock_logger.warning.assert_called_once()
    
    def test_extract_from_file_date_edge_cases(self, extractor):
        """Test date extraction edge cases."""
        test_cases = [
            ("20200229-leap-year.mp3", 2020, 2, 29),  # Leap year
            ("20250101-new-year.mp3", 2025, 1, 1),    # Year start
            ("20251231-year-end.mp3", 2025, 12, 31),  # Year end
        ]
        
        for filename, expected_year, expected_month, expected_day in test_cases:
            with patch('extract_metadata.os.path.exists', return_value=True), \
                 patch('extract_metadata.os.path.getsize', return_value=1000000), \
                 patch('extract_metadata.mutagen.File', return_value=None):
                
                result = extractor.extract_from_file(f"/test/{filename}")
                pub_date = datetime.fromisoformat(result['pub_date'])
                
                assert pub_date.year == expected_year
                assert pub_date.month == expected_month
                assert pub_date.day == expected_day


class TestMainFunction:
    """Test cases for main function."""
    
    @patch('extract_metadata.sys.argv')
    def test_main_with_valid_args(self, mock_argv, temporary_mp3_file):
        """Test main function with valid arguments."""
        # Create a test MP3 file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'ID3\x03\x00\x00\x00' + b'0' * 1000)
        
        # Rename to valid slug format
        import tempfile
        import os
        test_dir = os.path.dirname(temporary_mp3_file)
        test_file = os.path.join(test_dir, "20250618-test-episode.mp3")
        os.rename(temporary_mp3_file, test_file)
        
        with patch('extract_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                audio_file=test_file,
                base_url='https://cdn.test.com',
                commit_sha='abc1234567890'
            )
            
            with patch('extract_metadata.mutagen.File') as mock_mutagen:
                mock_audio = Mock()
                mock_audio.info.length = 1800.0
                mock_audio.tags = {'TIT2': ['Test Episode']}
                mock_mutagen.return_value = mock_audio
                
                with patch('extract_metadata.print') as mock_print:
                    from extract_metadata import main
                    main()
                    
                    # Verify GitHub Actions outputs were printed
                    output_calls = [str(call) for call in mock_print.call_args_list]
                    assert any('::set-output name=slug::' in call for call in output_calls)
                    assert any('::set-output name=title::' in call for call in output_calls)
                    assert any('::set-output name=guid::' in call for call in output_calls)
        
        # Cleanup
        if os.path.exists(test_file):
            os.unlink(test_file)
    
    def test_main_with_invalid_file(self):
        """Test main function with non-existent file."""
        with patch('extract_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                audio_file='/nonexistent/file.mp3',
                base_url='https://cdn.test.com',
                commit_sha='abc1234567890'
            )
            
            with patch('extract_metadata.sys.exit') as mock_exit:
                from extract_metadata import main
                main()
                mock_exit.assert_called_with(1)
    
    def test_main_with_invalid_slug(self, temporary_mp3_file):
        """Test main function with invalid slug format."""
        # Create file with invalid name
        invalid_file = temporary_mp3_file.replace('.mp3', '')
        invalid_file = f"{invalid_file[:-10]}invalid-slug.mp3"
        os.rename(temporary_mp3_file, invalid_file)
        
        with patch('extract_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                audio_file=invalid_file,
                base_url='https://cdn.test.com',
                commit_sha='abc1234567890'
            )
            
            with patch('extract_metadata.sys.exit') as mock_exit:
                from extract_metadata import main
                main()
                mock_exit.assert_called_with(1)
        
        # Cleanup
        if os.path.exists(invalid_file):
            os.unlink(invalid_file)


class TestSlugValidation:
    """Comprehensive tests for slug validation."""
    
    @pytest.fixture
    def extractor(self):
        return MetadataExtractor("https://test.com", "abc123")
    
    def test_slug_date_validation(self, extractor):
        """Test date component validation in slugs."""
        # Valid dates
        valid_dates = [
            "20250101-title",  # January 1st
            "20250228-title",  # February 28th (non-leap year)
            "20240229-title",  # February 29th (leap year)
            "20250630-title",  # June 30th
            "20251231-title",  # December 31st
        ]
        
        for slug in valid_dates:
            assert extractor._validate_slug_format(slug), f"Should be valid: {slug}"
        
        # Invalid dates
        invalid_dates = [
            "20250229-title",  # February 29th (non-leap year)
            "20250431-title",  # April 31st (doesn't exist)
            "20250632-title",  # Invalid month/day
            "20251301-title",  # Invalid month
            "20250000-title",  # Invalid day
            "99991231-title",  # Invalid year
        ]
        
        for slug in invalid_dates:
            assert not extractor._validate_slug_format(slug), f"Should be invalid: {slug}"
    
    def test_slug_title_validation(self, extractor):
        """Test title component validation in slugs."""
        # Valid titles
        valid_titles = [
            "20250618-a",  # Single character
            "20250618-episode-1",  # With number
            "20250618-very-long-episode-title-with-many-words",  # Long title
            "20250618-mix3d-numb3rs",  # Mixed alphanumeric
        ]
        
        for slug in valid_titles:
            assert extractor._validate_slug_format(slug), f"Should be valid: {slug}"
        
        # Invalid titles
        invalid_titles = [
            "20250618-",  # Empty title
            "20250618--double-dash",  # Double dash
            "20250618-title-",  # Ends with dash
            "20250618--start-dash",  # Starts with dash after date
            "20250618-CAPS",  # Uppercase
            "20250618-under_score",  # Underscore
            "20250618-space title",  # Space
            "20250618-special!",  # Special character
        ]
        
        for slug in invalid_titles:
            assert not extractor._validate_slug_format(slug), f"Should be invalid: {slug}"


class TestIntegration:
    """Integration tests for metadata extraction."""
    
    @pytest.mark.integration
    def test_real_mp3_metadata_extraction(self, temporary_directory):
        """Test metadata extraction with a realistic MP3 file structure."""
        # Create a more realistic MP3 file with ID3 header
        mp3_path = os.path.join(temporary_directory, "20250618-integration-test.mp3")
        
        with open(mp3_path, 'wb') as f:
            # Write minimal MP3 header with ID3v2.3
            f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')  # ID3v2.3 header
            f.write(b'\x00' * 1000)  # Padding
            f.write(b'\xFF\xFB\x90\x00')  # MP3 frame header
            f.write(b'\x00' * 100000)  # Audio data
        
        extractor = MetadataExtractor(
            base_url="https://cdn.integration.test",
            commit_sha="integration123"
        )
        
        with patch('extract_metadata.mutagen.File') as mock_mutagen:
            # Mock successful mutagen parsing
            mock_audio = Mock()
            mock_audio.info.length = 2400.0  # 40 minutes
            mock_audio.tags = {
                'TIT2': ['Integration Test Episode'],
                'COMM::eng': ['This is an integration test episode'],
            }
            mock_mutagen.return_value = mock_audio
            
            result = extractor.extract_from_file(mp3_path)
            
            # Verify all fields are present and correct
            assert result['slug'] == "20250618-integration-test"
            assert result['title'] == "Integration Test Episode"
            assert result['description'] == "This is an integration test episode"
            assert result['duration_seconds'] == 2400
            assert result['file_size_bytes'] > 100000  # Has actual file size
            assert result['audio_url'] == "https://cdn.integration.test/podcast/2025/20250618-integration-test.mp3"
            assert result['guid'] == "repo-integra-20250618-integration-test"
            assert result['s3_key'] == "podcast/2025/20250618-integration-test.mp3"
            assert result['year'] == 2025
            
            # Verify date is correctly parsed
            pub_date = datetime.fromisoformat(result['pub_date'])
            assert pub_date.year == 2025
            assert pub_date.month == 6
            assert pub_date.day == 18
            assert pub_date.tzinfo == timezone.utc


class TestEpisodeDirectoryExtraction:
    """Test cases for episode directory extraction functionality."""
    
    @pytest.fixture
    def extractor(self):
        """Create MetadataExtractor instance for testing."""
        return MetadataExtractor(
            base_url="https://cdn.test.com",
            commit_sha="abc1234567890"
        )
    
    def test_extract_from_directory_basic(self, extractor):
        """Test basic directory extraction functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-test-episode')
            os.makedirs(episode_dir)
            
            # Create dummy audio file
            audio_file = os.path.join(episode_dir, 'audio.mp3')
            with open(audio_file, 'w') as f:
                f.write('dummy audio content')
            
            # Create episode_data.json
            episode_data = {
                'title': 'Test Episode Title',
                'description': 'Test episode description',
                'season': 1,
                'episode_number': 5,
                'itunes_keywords': ['test', 'episode']
            }
            
            json_file = os.path.join(episode_dir, 'episode_data.json')
            with open(json_file, 'w') as f:
                json.dump(episode_data, f)
            
            # Test extraction
            with patch('mutagen.File') as mock_mutagen:
                mock_audio = Mock()
                mock_audio.info.length = 300
                mock_mutagen.return_value = mock_audio
                
                metadata = extractor.extract_from_directory(episode_dir)
                
                assert metadata['slug'] == '20250618-test-episode'
                assert metadata['title'] == 'Test Episode Title'
                assert metadata['description'] == 'Test episode description'
                assert metadata['season'] == 1
                assert metadata['episode_number'] == 5
                assert metadata['itunes_keywords'] == ['test', 'episode']
                assert metadata['duration_seconds'] == 300
                assert metadata['guid'] == 'repo-abc1234-20250618-test-episode'
                assert metadata['s3_base_path'] == 'podcast/2025/20250618-test-episode'
                assert metadata['audio_url'] == 'https://cdn.test.com/podcast/2025/20250618-test-episode/audio.mp3'
    
    def test_extract_from_directory_with_image(self, extractor):
        """Test directory extraction with episode image."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-test-episode')
            os.makedirs(episode_dir)
            
            # Create dummy files
            audio_file = os.path.join(episode_dir, 'audio.mp3')
            image_file = os.path.join(episode_dir, 'cover.jpg')
            
            with open(audio_file, 'w') as f:
                f.write('dummy audio')
            with open(image_file, 'w') as f:
                f.write('dummy image')
            
            # Create episode_data.json with image reference
            episode_data = {
                'title': 'Episode with Image',
                'description': 'Episode that has a custom image',
                'episode_image': 'cover.jpg'
            }
            
            json_file = os.path.join(episode_dir, 'episode_data.json')
            with open(json_file, 'w') as f:
                json.dump(episode_data, f)
            
            # Test extraction
            with patch('mutagen.File'):
                metadata = extractor.extract_from_directory(episode_dir)
                
                assert metadata['episode_image_url'] == 'https://cdn.test.com/podcast/2025/20250618-test-episode/cover.jpg'
    
    def test_extract_from_directory_no_json(self, extractor):
        """Test directory extraction without episode_data.json (fallback behavior)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-fallback-test')
            os.makedirs(episode_dir)
            
            # Create only audio file, no JSON
            audio_file = os.path.join(episode_dir, 'audio.wav')
            with open(audio_file, 'w') as f:
                f.write('dummy audio content')
            
            # Test extraction
            with patch('mutagen.File') as mock_mutagen:
                mock_audio = Mock()
                mock_audio.info.length = 180
                mock_mutagen.return_value = mock_audio
                
                metadata = extractor.extract_from_directory(episode_dir)
                
                # Should generate fallback values
                assert metadata['slug'] == '20250618-fallback-test'
                assert metadata['title'] == 'Fallback Test'  # Generated from slug (date prefix removed)
                assert metadata['description'] == 'Episode: Fallback Test'
                assert metadata['duration_seconds'] == 180
                assert metadata['file_extension'] == '.wav'
                assert metadata['audio_url'] == 'https://cdn.test.com/podcast/2025/20250618-fallback-test/audio.wav'
    
    def test_extract_from_directory_invalid_slug(self, extractor):
        """Test directory extraction with invalid slug format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory with invalid slug
            episode_dir = os.path.join(temp_dir, 'invalid-slug-format')
            os.makedirs(episode_dir)
            
            with pytest.raises(ValueError, match="Invalid slug format"):
                extractor.extract_from_directory(episode_dir)
    
    def test_extract_from_directory_no_audio_files(self, extractor):
        """Test directory extraction with no audio files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-no-audio')
            os.makedirs(episode_dir)
            
            # Create only non-audio files
            with open(os.path.join(episode_dir, 'readme.txt'), 'w') as f:
                f.write('readme')
            
            with pytest.raises(ValueError, match="No audio files"):
                extractor.extract_from_directory(episode_dir)
    
    def test_extract_from_directory_invalid_json(self, extractor):
        """Test directory extraction with invalid JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create episode directory
            episode_dir = os.path.join(temp_dir, '20250618-bad-json')
            os.makedirs(episode_dir)
            
            # Create audio file
            with open(os.path.join(episode_dir, 'audio.mp3'), 'w') as f:
                f.write('dummy audio')
            
            # Create invalid JSON file
            json_file = os.path.join(episode_dir, 'episode_data.json')
            with open(json_file, 'w') as f:
                f.write('{ invalid json content }')
            
            with patch('mutagen.File'):
                # Should not raise exception, should use fallback values
                metadata = extractor.extract_from_directory(episode_dir)
                
                # Should use generated title since JSON parsing failed
                assert metadata['title'] == 'Bad Json'