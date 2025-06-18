"""
Tests for metadata validation script (validate_metadata.py).

This module tests the episode metadata validation functionality including:
- Required fields validation
- Format validation for various fields
- Content validation and sanity checks
- Error reporting and warning generation
"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from validate_metadata import MetadataValidator


class TestMetadataValidator:
    """Test cases for MetadataValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create MetadataValidator instance for testing."""
        return MetadataValidator()
    
    def test_validator_initialization(self, validator):
        """Test MetadataValidator initialization."""
        assert validator.errors == []
        assert validator.warnings == []
    
    def test_validate_with_valid_metadata(self, validator, sample_episode_metadata):
        """Test validation with completely valid metadata."""
        result = validator.validate(sample_episode_metadata)
        
        assert result is True
        assert len(validator.errors) == 0
        assert len(validator.warnings) == 0
    
    def test_validate_with_missing_required_fields(self, validator):
        """Test validation with missing required fields."""
        incomplete_metadata = {
            'slug': '20250618-test',
            'title': 'Test Episode'
            # Missing other required fields
        }
        
        result = validator.validate(incomplete_metadata)
        
        assert result is False
        assert len(validator.errors) > 0
        
        # Check for specific missing field errors
        error_messages = [error for error in validator.errors]
        assert any('Missing required field: description' in error for error in error_messages)
        assert any('Missing required field: pub_date' in error for error in error_messages)
        assert any('Missing required field: duration_seconds' in error for error in error_messages)
        assert any('Missing required field: file_size_bytes' in error for error in error_messages)
        assert any('Missing required field: audio_url' in error for error in error_messages)
        assert any('Missing required field: guid' in error for error in error_messages)
        assert any('Missing required field: s3_key' in error for error in error_messages)
    
    def test_validate_with_null_required_fields(self, validator):
        """Test validation with null required fields."""
        null_metadata = {
            'slug': None,
            'title': None,
            'description': None,
            'pub_date': None,
            'duration_seconds': None,
            'file_size_bytes': None,
            'audio_url': None,
            'guid': None,
            's3_key': None
        }
        
        result = validator.validate(null_metadata)
        
        assert result is False
        assert len(validator.errors) == 9  # All required fields are null


class TestSlugValidation:
    """Test cases for slug format validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_slug_format_valid(self, validator):
        """Test valid slug formats."""
        valid_metadata_samples = [
            {'slug': '20250618-test-episode', **self._minimal_metadata()},
            {'slug': '20250101-new-year-special', **self._minimal_metadata()},
            {'slug': '20251231-year-end-review', **self._minimal_metadata()},
            {'slug': '20250630-episode-100', **self._minimal_metadata()},
        ]
        
        for metadata in valid_metadata_samples:
            validator.errors = []
            validator.warnings = []
            result = validator.validate(metadata)
            
            # Should not have slug-related errors
            slug_errors = [e for e in validator.errors if 'slug' in e.lower()]
            assert len(slug_errors) == 0, f"Unexpected slug error for {metadata['slug']}: {slug_errors}"
    
    def test_validate_slug_format_invalid(self, validator):
        """Test invalid slug formats."""
        invalid_slugs = [
            'too-short',
            '2025061-missing-digit',
            '20250618',  # No title part
            '20250618-',  # Empty title
            '20250632-invalid-date',  # Invalid date (32nd day)
            '20251301-invalid-month',  # Invalid month (13th month)
            '20250618-UPPERCASE',  # Uppercase not allowed
            '20250618-with_underscore',  # Underscore not allowed
            '20250618--double-dash',  # Double dash
            '20250618-title-',  # Ends with dash
        ]
        
        for slug in invalid_slugs:
            validator.errors = []
            validator.warnings = []
            metadata = {'slug': slug, **self._minimal_metadata()}
            
            result = validator.validate(metadata)
            
            # Should have slug-related errors
            slug_errors = [e for e in validator.errors if 'slug' in e.lower() or 'date' in e.lower() or 'kebab' in e.lower()]
            assert len(slug_errors) > 0, f"Expected slug error for {slug} but got none"
    
    def test_validate_slug_date_validation(self, validator):
        """Test date validation within slug."""
        # Test leap year
        metadata = {'slug': '20240229-leap-year', **self._minimal_metadata()}
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        # Should be valid (2024 is a leap year)
        date_errors = [e for e in validator.errors if 'date' in e.lower()]
        assert len(date_errors) == 0
        
        # Test non-leap year
        metadata = {'slug': '20250229-not-leap-year', **self._minimal_metadata()}
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        # Should be invalid (2025 is not a leap year)
        date_errors = [e for e in validator.errors if 'date' in e.lower()]
        assert len(date_errors) > 0
    
    def _minimal_metadata(self):
        """Return minimal valid metadata excluding slug."""
        return {
            'title': 'Test Episode',
            'description': 'Test description',
            'pub_date': '2025-06-18T10:00:00+00:00',
            'duration_seconds': 1800,
            'file_size_bytes': 25000000,
            'audio_url': 'https://cdn.test.com/test.mp3',
            'guid': 'repo-abc123-test',
            's3_key': 'podcast/2025/test.mp3'
        }


class TestTitleValidation:
    """Test cases for title validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_title_valid(self, validator, sample_episode_metadata):
        """Test valid title validation."""
        valid_titles = [
            'Short',
            'Medium Length Episode Title',
            'Very Long Episode Title That Still Should Be Acceptable Because It Contains Good Content',
            'Episode with Numbers 123',
            'Special Characters: - & + ()[]',
        ]
        
        for title in valid_titles:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'title': title}
            
            result = validator.validate(metadata)
            
            # Should not have title-related errors
            title_errors = [e for e in validator.errors if 'title' in e.lower()]
            assert len(title_errors) == 0, f"Unexpected title error for '{title}': {title_errors}"
    
    def test_validate_title_too_short(self, validator, sample_episode_metadata):
        """Test title that is too short."""
        metadata = {**sample_episode_metadata, 'title': 'AB'}  # Only 2 characters
        
        result = validator.validate(metadata)
        
        assert result is False
        title_errors = [e for e in validator.errors if 'title' in e.lower() and 'short' in e.lower()]
        assert len(title_errors) > 0
    
    def test_validate_title_too_long(self, validator, sample_episode_metadata):
        """Test title that is too long."""
        long_title = 'A' * 300  # 300 characters, over the 255 limit
        metadata = {**sample_episode_metadata, 'title': long_title}
        
        result = validator.validate(metadata)
        
        assert result is False
        title_errors = [e for e in validator.errors if 'title' in e.lower() and 'long' in e.lower()]
        assert len(title_errors) > 0
    
    def test_validate_title_whitespace_warnings(self, validator, sample_episode_metadata):
        """Test title with whitespace issues generates warnings."""
        titles_with_whitespace = [
            '  Title with leading spaces',
            'Title with trailing spaces  ',
            '  Title with both  ',
        ]
        
        for title in titles_with_whitespace:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'title': title}
            
            result = validator.validate(metadata)
            
            # Should pass validation but generate warnings
            assert result is True  # No errors
            whitespace_warnings = [w for w in validator.warnings if 'whitespace' in w.lower()]
            assert len(whitespace_warnings) > 0, f"Expected whitespace warning for '{title}'"
    
    def test_validate_title_all_caps_warning(self, validator, sample_episode_metadata):
        """Test title in all caps generates warning."""
        metadata = {**sample_episode_metadata, 'title': 'THIS IS ALL UPPERCASE TITLE'}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        caps_warnings = [w for w in validator.warnings if 'uppercase' in w.lower()]
        assert len(caps_warnings) > 0


class TestDescriptionValidation:
    """Test cases for description validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_description_length_warnings(self, validator, sample_episode_metadata):
        """Test description length validation."""
        # Very short description
        short_desc = 'Short'  # 5 characters
        metadata = {**sample_episode_metadata, 'description': short_desc}
        
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        assert result is True
        short_warnings = [w for w in validator.warnings if 'short' in w.lower()]
        assert len(short_warnings) > 0
        
        # Very long description
        long_desc = 'A' * 5000  # 5000 characters
        metadata = {**sample_episode_metadata, 'description': long_desc}
        
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        assert result is True
        long_warnings = [w for w in validator.warnings if 'long' in w.lower()]
        assert len(long_warnings) > 0
    
    def test_validate_description_whitespace(self, validator, sample_episode_metadata):
        """Test description with whitespace issues."""
        desc_with_whitespace = '  Description with leading and trailing spaces  '
        metadata = {**sample_episode_metadata, 'description': desc_with_whitespace}
        
        result = validator.validate(metadata)
        
        assert result is True
        whitespace_warnings = [w for w in validator.warnings if 'whitespace' in w.lower()]
        assert len(whitespace_warnings) > 0


class TestDateValidation:
    """Test cases for publication date validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_pub_date_valid_formats(self, validator, sample_episode_metadata):
        """Test valid publication date formats."""
        valid_dates = [
            '2025-06-18T10:00:00+00:00',  # ISO format with timezone
            '2025-06-18T10:00:00Z',       # ISO format with Z
            '2025-06-18T10:00:00.000Z',   # ISO format with milliseconds
            '2025-01-01T00:00:00+00:00',  # Year start
            '2025-12-31T23:59:59+00:00',  # Year end
        ]
        
        for date_str in valid_dates:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'pub_date': date_str}
            
            result = validator.validate(metadata)
            
            # Should not have date-related errors
            date_errors = [e for e in validator.errors if 'date' in e.lower()]
            assert len(date_errors) == 0, f"Unexpected date error for '{date_str}': {date_errors}"
    
    def test_validate_pub_date_invalid_formats(self, validator, sample_episode_metadata):
        """Test invalid publication date formats."""
        invalid_dates = [
            '2025-06-18',                 # Missing time
            '2025/06/18 10:00:00',        # Wrong format
            '18-06-2025T10:00:00Z',       # Wrong order
            'invalid-date-string',        # Completely invalid
            '2025-13-01T10:00:00Z',       # Invalid month
            '2025-06-32T10:00:00Z',       # Invalid day
        ]
        
        for date_str in invalid_dates:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'pub_date': date_str}
            
            result = validator.validate(metadata)
            
            # Should have date-related errors
            date_errors = [e for e in validator.errors if 'date' in e.lower()]
            assert len(date_errors) > 0, f"Expected date error for '{date_str}' but got none"
    
    def test_validate_pub_date_future_warning(self, validator, sample_episode_metadata):
        """Test future publication date generates warning."""
        # Use a date far in the future
        future_date = '2030-01-01T10:00:00+00:00'
        metadata = {**sample_episode_metadata, 'pub_date': future_date}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        future_warnings = [w for w in validator.warnings if 'future' in w.lower()]
        assert len(future_warnings) > 0
    
    def test_validate_pub_date_very_old_warning(self, validator, sample_episode_metadata):
        """Test very old publication date generates warning."""
        # Use a date from 20 years ago
        old_date = '2005-01-01T10:00:00+00:00'
        metadata = {**sample_episode_metadata, 'pub_date': old_date}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        old_warnings = [w for w in validator.warnings if 'old' in w.lower()]
        assert len(old_warnings) > 0


class TestDurationValidation:
    """Test cases for duration validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_duration_valid(self, validator, sample_episode_metadata):
        """Test valid duration values."""
        valid_durations = [60, 300, 1800, 3600, 7200]  # 1 min to 2 hours
        
        for duration in valid_durations:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'duration_seconds': duration}
            
            result = validator.validate(metadata)
            
            # Should not have duration-related errors
            duration_errors = [e for e in validator.errors if 'duration' in e.lower()]
            assert len(duration_errors) == 0, f"Unexpected duration error for {duration}: {duration_errors}"
    
    def test_validate_duration_negative(self, validator, sample_episode_metadata):
        """Test negative duration generates error."""
        metadata = {**sample_episode_metadata, 'duration_seconds': -1}
        
        result = validator.validate(metadata)
        
        assert result is False
        duration_errors = [e for e in validator.errors if 'duration' in e.lower() and 'negative' in e.lower()]
        assert len(duration_errors) > 0
    
    def test_validate_duration_zero_warning(self, validator, sample_episode_metadata):
        """Test zero duration generates warning."""
        metadata = {**sample_episode_metadata, 'duration_seconds': 0}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        zero_warnings = [w for w in validator.warnings if 'duration' in w.lower() and '0' in w]
        assert len(zero_warnings) > 0
    
    def test_validate_duration_very_short_warning(self, validator, sample_episode_metadata):
        """Test very short duration generates warning."""
        metadata = {**sample_episode_metadata, 'duration_seconds': 30}  # 30 seconds
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        short_warnings = [w for w in validator.warnings if 'short' in w.lower()]
        assert len(short_warnings) > 0
    
    def test_validate_duration_very_long_warning(self, validator, sample_episode_metadata):
        """Test very long duration generates warning."""
        metadata = {**sample_episode_metadata, 'duration_seconds': 18000}  # 5 hours
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        long_warnings = [w for w in validator.warnings if 'long' in w.lower()]
        assert len(long_warnings) > 0
    
    def test_validate_duration_invalid_type(self, validator, sample_episode_metadata):
        """Test invalid duration type generates error."""
        invalid_durations = ['not_a_number', 'abc', None, [1800]]
        
        for duration in invalid_durations:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'duration_seconds': duration}
            
            result = validator.validate(metadata)
            
            # Should have duration-related errors
            duration_errors = [e for e in validator.errors if 'duration' in e.lower()]
            assert len(duration_errors) > 0, f"Expected duration error for {duration} but got none"


class TestFileSizeValidation:
    """Test cases for file size validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_file_size_valid(self, validator, sample_episode_metadata):
        """Test valid file size values."""
        valid_sizes = [
            5 * 1024 * 1024,      # 5 MB
            25 * 1024 * 1024,     # 25 MB
            100 * 1024 * 1024,    # 100 MB
        ]
        
        for size in valid_sizes:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'file_size_bytes': size}
            
            result = validator.validate(metadata)
            
            # Should not have file size related errors
            size_errors = [e for e in validator.errors if 'file size' in e.lower()]
            assert len(size_errors) == 0, f"Unexpected file size error for {size}: {size_errors}"
    
    def test_validate_file_size_negative_or_zero(self, validator, sample_episode_metadata):
        """Test negative or zero file size generates error."""
        invalid_sizes = [-1, 0]
        
        for size in invalid_sizes:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'file_size_bytes': size}
            
            result = validator.validate(metadata)
            
            assert result is False
            size_errors = [e for e in validator.errors if 'file size' in e.lower()]
            assert len(size_errors) > 0, f"Expected file size error for {size}"
    
    def test_validate_file_size_very_small_warning(self, validator, sample_episode_metadata):
        """Test very small file size generates warning."""
        metadata = {**sample_episode_metadata, 'file_size_bytes': 500 * 1024}  # 500 KB
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        small_warnings = [w for w in validator.warnings if 'small' in w.lower()]
        assert len(small_warnings) > 0
    
    def test_validate_file_size_very_large_warning(self, validator, sample_episode_metadata):
        """Test very large file size generates warning."""
        metadata = {**sample_episode_metadata, 'file_size_bytes': 600 * 1024 * 1024}  # 600 MB
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        large_warnings = [w for w in validator.warnings if 'large' in w.lower()]
        assert len(large_warnings) > 0


class TestUrlAndGuidValidation:
    """Test cases for URL and GUID validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_audio_url_valid(self, validator, sample_episode_metadata):
        """Test valid audio URL formats."""
        valid_urls = [
            'https://cdn.example.com/podcast.mp3',
            'http://example.com/episodes/episode.mp3',
            'https://subdomain.domain.co.uk/path/to/file.mp3',
            'https://cdn.example.com/episode.wav',  # WAV files are now supported
        ]
        
        for url in valid_urls:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'audio_url': url}
            
            result = validator.validate(metadata)
            
            # Should not have URL-related errors
            url_errors = [e for e in validator.errors if 'url' in e.lower()]
            assert len(url_errors) == 0, f"Unexpected URL error for '{url}': {url_errors}"
    
    def test_validate_audio_url_invalid(self, validator, sample_episode_metadata):
        """Test invalid audio URL formats."""
        invalid_urls = [
            'not-a-url',
            'ftp://example.com/file.mp3',  # Wrong protocol
            'https://example.com/file.txt',  # Wrong extension
            'https://example.com/file with spaces.mp3',  # Spaces in URL
        ]
        
        for url in invalid_urls:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 'audio_url': url}
            
            result = validator.validate(metadata)
            
            # Should have URL-related errors
            url_errors = [e for e in validator.errors if 'url' in e.lower()]
            assert len(url_errors) > 0, f"Expected URL error for '{url}' but got none"
    
    def test_validate_guid_format(self, validator, sample_episode_metadata):
        """Test GUID format validation."""
        # Valid GUID
        valid_guid = 'repo-abc1234-20250618-test-episode'
        metadata = {**sample_episode_metadata, 'guid': valid_guid}
        
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        # Should not have GUID-related errors
        guid_errors = [e for e in validator.errors if 'guid' in e.lower()]
        assert len(guid_errors) == 0
        
        # Invalid GUID - wrong format
        invalid_guid = 'wrong-format-guid'
        metadata = {**sample_episode_metadata, 'guid': invalid_guid}
        
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        # Should have GUID-related errors
        guid_errors = [e for e in validator.errors if 'guid' in e.lower()]
        assert len(guid_errors) > 0
    
    def test_validate_guid_sha_length_warning(self, validator, sample_episode_metadata):
        """Test GUID SHA part length generates warning."""
        # GUID with short SHA
        short_sha_guid = 'repo-abc-20250618-test-episode'  # SHA only 3 chars
        metadata = {**sample_episode_metadata, 'guid': short_sha_guid}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        sha_warnings = [w for w in validator.warnings if 'sha' in w.lower()]
        assert len(sha_warnings) > 0


class TestS3KeyValidation:
    """Test cases for S3 key validation."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_s3_key_valid(self, validator, sample_episode_metadata):
        """Test valid S3 key formats."""
        valid_keys = [
            'podcast/2025/20250618-test-episode.mp3',
            'podcast/2024/20241201-year-end.mp3',
            'podcast/2026/20260101-new-year.mp3',
            'podcast/2025/20250618-test-episode.wav',  # WAV files are now supported
        ]
        
        for key in valid_keys:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 's3_key': key}
            
            result = validator.validate(metadata)
            
            # Should not have S3 key related errors
            s3_errors = [e for e in validator.errors if 's3' in e.lower()]
            assert len(s3_errors) == 0, f"Unexpected S3 key error for '{key}': {s3_errors}"
    
    def test_validate_s3_key_invalid_format(self, validator, sample_episode_metadata):
        """Test invalid S3 key formats."""
        invalid_keys = [
            'wrong/path/file.mp3',        # Wrong prefix
            'podcast/2025/file.txt',      # Wrong extension
            'podcast/year/file.mp3',      # Non-numeric year
            'podcast/2025',               # Missing filename
            'podcast/2025/file',          # Missing extension
        ]
        
        for key in invalid_keys:
            validator.errors = []
            validator.warnings = []
            metadata = {**sample_episode_metadata, 's3_key': key}
            
            result = validator.validate(metadata)
            
            # Should have S3 key related errors
            s3_errors = [e for e in validator.errors if 's3' in e.lower()]
            assert len(s3_errors) > 0, f"Expected S3 key error for '{key}' but got none"
    
    def test_validate_s3_key_unreasonable_year(self, validator, sample_episode_metadata):
        """Test S3 key with unreasonable year generates warning."""
        # Very old year
        old_key = 'podcast/1999/19991231-old-episode.mp3'
        metadata = {**sample_episode_metadata, 's3_key': old_key}
        
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        year_warnings = [w for w in validator.warnings if 'year' in w.lower()]
        assert len(year_warnings) > 0
        
        # Future year
        future_key = 'podcast/2030/20301231-future-episode.mp3'
        metadata = {**sample_episode_metadata, 's3_key': future_key}
        
        validator.errors = []
        validator.warnings = []
        result = validator.validate(metadata)
        
        assert result is True  # No errors
        year_warnings = [w for w in validator.warnings if 'year' in w.lower()]
        assert len(year_warnings) > 0


class TestMainFunction:
    """Test cases for main function."""
    
    def test_main_with_valid_metadata(self, sample_episode_metadata):
        """Test main function with valid metadata."""
        metadata_json = json.dumps(sample_episode_metadata)
        
        with patch('validate_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(metadata=metadata_json)
            
            with patch('validate_metadata.sys.exit') as mock_exit:
                from validate_metadata import main
                main()
                
                # Should exit with 0 (success)
                mock_exit.assert_called_with(0)
    
    def test_main_with_invalid_metadata(self, invalid_episode_metadata):
        """Test main function with invalid metadata."""
        metadata_json = json.dumps(invalid_episode_metadata)
        
        with patch('validate_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(metadata=metadata_json)
            
            with patch('validate_metadata.sys.exit') as mock_exit, \
                 patch('validate_metadata.print') as mock_print:
                from validate_metadata import main
                main()
                
                # Should exit with 1 (failure)
                mock_exit.assert_called_with(1)
                
                # Should print error outputs
                output_calls = [str(call) for call in mock_print.call_args_list]
                assert any('::error title=Validation Error::' in call for call in output_calls)
    
    def test_main_with_invalid_json(self):
        """Test main function with invalid JSON."""
        with patch('validate_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(metadata='invalid json')
            
            with patch('validate_metadata.sys.exit') as mock_exit:
                from validate_metadata import main
                main()
                
                # Should exit with 1 (failure)
                mock_exit.assert_called_with(1)
    
    def test_main_with_validation_warnings(self, sample_episode_metadata):
        """Test main function with metadata that has warnings."""
        # Add whitespace to title to generate warning
        sample_episode_metadata['title'] = '  Test Episode  '
        metadata_json = json.dumps(sample_episode_metadata)
        
        with patch('validate_metadata.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(metadata=metadata_json)
            
            with patch('validate_metadata.sys.exit') as mock_exit, \
                 patch('validate_metadata.print') as mock_print:
                from validate_metadata import main
                main()
                
                # Should exit with 0 (success) despite warnings
                mock_exit.assert_called_with(0)
                
                # Should print warning outputs
                output_calls = [str(call) for call in mock_print.call_args_list]
                assert any('::warning title=Validation Warning::' in call for call in output_calls)


class TestEdgeCases:
    """Test cases for edge cases and boundary conditions."""
    
    @pytest.fixture
    def validator(self):
        return MetadataValidator()
    
    def test_validate_empty_metadata(self, validator):
        """Test validation with completely empty metadata."""
        result = validator.validate({})
        
        assert result is False
        assert len(validator.errors) >= 9  # All required fields missing
    
    def test_validate_metadata_with_extra_fields(self, validator, sample_episode_metadata):
        """Test validation with extra fields (should be ignored)."""
        metadata_with_extras = {
            **sample_episode_metadata,
            'extra_field': 'extra_value',
            'another_extra': 123,
            'nested_extra': {'key': 'value'}
        }
        
        result = validator.validate(metadata_with_extras)
        
        # Should still pass validation (extra fields ignored)
        assert result is True
    
    def test_validate_boundary_values(self, validator, sample_episode_metadata):
        """Test validation with boundary values."""
        # Minimum valid title length
        metadata = {**sample_episode_metadata, 'title': 'ABC'}  # 3 characters
        result = validator.validate(metadata)
        assert result is True
        
        # Maximum valid title length
        metadata = {**sample_episode_metadata, 'title': 'A' * 255}  # 255 characters
        result = validator.validate(metadata)
        assert result is True
        
        # Minimum reasonable file size
        metadata = {**sample_episode_metadata, 'file_size_bytes': 1024 * 1024}  # 1 MB
        result = validator.validate(metadata)
        assert result is True