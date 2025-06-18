"""
Tests for S3 upload script (upload_s3.py).

This module tests the S3 upload functionality including:
- File upload with retry logic
- Error handling and recovery
- Upload verification
- Metadata handling
- Bucket validation
"""

import json
import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import ClientError, NoCredentialsError

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from upload_s3 import S3Uploader


class TestS3Uploader:
    """Test cases for S3Uploader class."""
    
    def test_uploader_initialization_success(self):
        """Test successful S3Uploader initialization."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            uploader = S3Uploader("test-bucket", "us-east-1")
            
            assert uploader.bucket_name == "test-bucket"
            assert uploader.region == "us-east-1"
            assert uploader.s3_client == mock_client
            mock_boto3.assert_called_once_with('s3', region_name='us-east-1')
    
    def test_uploader_initialization_no_region(self):
        """Test S3Uploader initialization without region."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            uploader = S3Uploader("test-bucket")
            
            assert uploader.bucket_name == "test-bucket"
            assert uploader.region is None
            mock_boto3.assert_called_once_with('s3')
    
    def test_uploader_initialization_no_credentials(self):
        """Test S3Uploader initialization with no credentials."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_boto3.side_effect = NoCredentialsError()
            
            with pytest.raises(ValueError, match="AWS credentials not found"):
                S3Uploader("test-bucket")
    
    def test_upload_with_retry_success_first_attempt(self, temporary_mp3_file):
        """Test successful upload on first attempt."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # Mock successful upload and verification
            mock_client.upload_file.return_value = None
            mock_client.head_object.return_value = {'ContentLength': 1000}
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=3
            )
            
            assert result['success'] is True
            assert result['bucket'] == "test-bucket"
            assert result['s3_key'] == "test/episode.mp3"
            assert result['file_size'] == 1000
            assert result['attempts'] == 1
            assert 'upload_duration' in result
            assert 'url' in result
            
            # Verify S3 calls
            mock_client.upload_file.assert_called_once()
            mock_client.head_object.assert_called_once()
    
    def test_upload_with_retry_failure_then_success(self, temporary_mp3_file):
        """Test upload failure followed by success (retry logic)."""
        with patch('upload_s3.boto3.client') as mock_boto3, \
             patch('upload_s3.time.sleep') as mock_sleep:
            
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # First attempt fails, second succeeds
            mock_client.upload_file.side_effect = [
                ClientError(
                    error_response={'Error': {'Code': 'ServiceUnavailable'}},
                    operation_name='PutObject'
                ),
                None  # Success on second attempt
            ]
            mock_client.head_object.return_value = {'ContentLength': 1000}
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=3
            )
            
            assert result['success'] is True
            assert result['attempts'] == 2
            
            # Verify retry behavior
            assert mock_client.upload_file.call_count == 2
            mock_sleep.assert_called_once_with(1)  # Exponential backoff: 2^(1-1) = 1
    
    def test_upload_with_retry_all_attempts_fail(self, temporary_mp3_file):
        """Test upload failure on all retry attempts."""
        with patch('upload_s3.boto3.client') as mock_boto3, \
             patch('upload_s3.time.sleep') as mock_sleep:
            
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # All attempts fail
            mock_client.upload_file.side_effect = ClientError(
                error_response={'Error': {'Code': 'AccessDenied'}},
                operation_name='PutObject'
            )
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=3
            )
            
            assert result['success'] is False
            assert result['attempts'] == 3
            assert 'error' in result
            
            # Verify all attempts were made
            assert mock_client.upload_file.call_count == 3
            # Verify exponential backoff: 1, 2 seconds
            expected_sleep_calls = [call(1), call(2)]
            mock_sleep.assert_has_calls(expected_sleep_calls)
    
    def test_upload_with_retry_exponential_backoff(self, temporary_mp3_file):
        """Test exponential backoff timing in retry logic."""
        with patch('upload_s3.boto3.client') as mock_boto3, \
             patch('upload_s3.time.sleep') as mock_sleep:
            
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # All attempts fail
            mock_client.upload_file.side_effect = Exception("Network error")
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=4
            )
            
            assert result['success'] is False
            
            # Verify exponential backoff: 1, 2, 4 seconds
            expected_sleep_calls = [call(1), call(2), call(4)]
            mock_sleep.assert_has_calls(expected_sleep_calls)
    
    def test_upload_with_retry_file_not_found(self):
        """Test upload with non-existent file."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            uploader = S3Uploader("test-bucket")
            
            with pytest.raises(FileNotFoundError, match="Local file not found"):
                uploader.upload_with_retry(
                    local_file="/nonexistent/file.mp3",
                    s3_key="test/episode.mp3"
                )
    
    def test_upload_with_retry_custom_metadata(self, temporary_mp3_file):
        """Test upload with custom metadata."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.upload_file.return_value = None
            mock_client.head_object.return_value = {'ContentLength': 1000}
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            metadata = {
                'title': 'Test Episode',
                'description': 'Test description',
                'duration': '1800'
            }
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                metadata=metadata
            )
            
            assert result['success'] is True
            
            # Verify upload_file was called with metadata
            upload_call_args = mock_client.upload_file.call_args
            extra_args = upload_call_args[1]['ExtraArgs']
            assert extra_args['Metadata'] == metadata
            assert extra_args['ContentType'] == 'audio/mpeg'
            assert extra_args['CacheControl'] == 'public, max-age=300'
            assert extra_args['ACL'] == 'public-read'
    
    def test_verify_upload_success(self):
        """Test successful upload verification."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_object.return_value = {'ContentLength': 1000}
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader._verify_upload("test/episode.mp3", 1000)
            
            assert result is True
            mock_client.head_object.assert_called_once_with(
                Bucket="test-bucket",
                Key="test/episode.mp3"
            )
    
    def test_verify_upload_size_mismatch(self):
        """Test upload verification with size mismatch."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_object.return_value = {'ContentLength': 500}  # Wrong size
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader._verify_upload("test/episode.mp3", 1000)
            
            assert result is False
    
    def test_verify_upload_client_error(self):
        """Test upload verification with client error."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_object.side_effect = ClientError(
                error_response={'Error': {'Code': 'NoSuchKey'}},
                operation_name='HeadObject'
            )
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader._verify_upload("test/episode.mp3", 1000)
            
            assert result is False
    
    def test_update_object_metadata_success(self):
        """Test successful object metadata update."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.copy_object.return_value = None
            
            uploader = S3Uploader("test-bucket")
            
            metadata = {
                'title': 'Updated Title',
                'description': 'Updated description'
            }
            
            result = uploader.update_object_metadata("test/episode.mp3", metadata)
            
            assert result is True
            
            # Verify copy_object call
            mock_client.copy_object.assert_called_once()
            copy_call_args = mock_client.copy_object.call_args
            assert copy_call_args[1]['Metadata'] == metadata
            assert copy_call_args[1]['MetadataDirective'] == 'REPLACE'
            assert copy_call_args[1]['ACL'] == 'public-read'
            assert copy_call_args[1]['ContentType'] == 'audio/mpeg'
            assert copy_call_args[1]['CacheControl'] == 'public, max-age=300'
    
    def test_update_object_metadata_error(self):
        """Test object metadata update with error."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.copy_object.side_effect = ClientError(
                error_response={'Error': {'Code': 'AccessDenied'}},
                operation_name='CopyObject'
            )
            
            uploader = S3Uploader("test-bucket")
            
            metadata = {'title': 'Test'}
            result = uploader.update_object_metadata("test/episode.mp3", metadata)
            
            assert result is False
    
    def test_check_bucket_exists_success(self):
        """Test successful bucket existence check."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_bucket.return_value = None
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.check_bucket_exists()
            
            assert result is True
            mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
    
    def test_check_bucket_exists_not_found(self):
        """Test bucket existence check with bucket not found."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_bucket.side_effect = ClientError(
                error_response={'Error': {'Code': '404'}},
                operation_name='HeadBucket'
            )
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.check_bucket_exists()
            
            assert result is False
    
    def test_check_bucket_exists_access_denied(self):
        """Test bucket existence check with access denied."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.head_bucket.side_effect = ClientError(
                error_response={'Error': {'Code': '403'}},
                operation_name='HeadBucket'
            )
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.check_bucket_exists()
            
            assert result is False
    
    def test_get_bucket_region_success(self):
        """Test successful bucket region retrieval."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.get_bucket_location.return_value = {'LocationConstraint': 'us-west-2'}
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.get_bucket_region()
            
            assert result == 'us-west-2'
    
    def test_get_bucket_region_us_east_1(self):
        """Test bucket region retrieval for us-east-1 (returns None)."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.get_bucket_location.return_value = {'LocationConstraint': None}
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.get_bucket_region()
            
            assert result == 'us-east-1'
    
    def test_get_bucket_region_error(self):
        """Test bucket region retrieval with error."""
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            mock_client.get_bucket_location.side_effect = ClientError(
                error_response={'Error': {'Code': 'AccessDenied'}},
                operation_name='GetBucketLocation'
            )
            
            uploader = S3Uploader("test-bucket")
            
            result = uploader.get_bucket_region()
            
            assert result is None


class TestMainFunction:
    """Test cases for main function."""
    
    def test_main_with_valid_args_success(self, temporary_mp3_file):
        """Test main function with valid arguments and successful upload."""
        # Create test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'0' * 1000)
        
        with patch('upload_s3.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('upload_s3.S3Uploader') as mock_uploader_class:
            
            mock_args.return_value = Mock(
                mp3_file=temporary_mp3_file,
                s3_key='test/episode.mp3',
                bucket='test-bucket',
                max_retries=3,
                metadata=None
            )
            
            mock_uploader = Mock()
            mock_uploader_class.return_value = mock_uploader
            mock_uploader.check_bucket_exists.return_value = True
            mock_uploader.upload_with_retry.return_value = {
                'success': True,
                'url': 'https://test-bucket.s3.amazonaws.com/test/episode.mp3',
                'upload_duration': 1.5,
                'attempts': 1,
                'file_size': 1000
            }
            
            with patch('upload_s3.print') as mock_print:
                from upload_s3 import main
                main()
                
                # Verify GitHub Actions outputs were printed
                output_calls = [str(call) for call in mock_print.call_args_list]
                assert any('::set-output name=mp3-url::' in call for call in output_calls)
                assert any('::set-output name=duration::' in call for call in output_calls)
                assert any('::set-output name=attempts::' in call for call in output_calls)
                assert any('::set-output name=file-size::' in call for call in output_calls)
    
    def test_main_with_bucket_not_exists(self, temporary_mp3_file):
        """Test main function with non-existent bucket."""
        # Create test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'0' * 1000)
        
        with patch('upload_s3.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('upload_s3.S3Uploader') as mock_uploader_class:
            
            mock_args.return_value = Mock(
                mp3_file=temporary_mp3_file,
                s3_key='test/episode.mp3',
                bucket='nonexistent-bucket',
                max_retries=3,
                metadata=None
            )
            
            mock_uploader = Mock()
            mock_uploader_class.return_value = mock_uploader
            mock_uploader.check_bucket_exists.return_value = False
            
            with patch('upload_s3.sys.exit') as mock_exit:
                from upload_s3 import main
                main()
                mock_exit.assert_called_with(1)
    
    def test_main_with_upload_failure(self, temporary_mp3_file):
        """Test main function with upload failure."""
        # Create test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'0' * 1000)
        
        with patch('upload_s3.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('upload_s3.S3Uploader') as mock_uploader_class:
            
            mock_args.return_value = Mock(
                mp3_file=temporary_mp3_file,
                s3_key='test/episode.mp3',
                bucket='test-bucket',
                max_retries=3,
                metadata=None
            )
            
            mock_uploader = Mock()
            mock_uploader_class.return_value = mock_uploader
            mock_uploader.check_bucket_exists.return_value = True
            mock_uploader.upload_with_retry.return_value = {
                'success': False,
                'error': 'Upload failed after 3 attempts',
                'attempts': 3
            }
            
            with patch('upload_s3.sys.exit') as mock_exit:
                from upload_s3 import main
                main()
                mock_exit.assert_called_with(1)
    
    def test_main_with_metadata(self, temporary_mp3_file):
        """Test main function with metadata parameter."""
        # Create test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'0' * 1000)
        
        metadata_json = json.dumps({
            'title': 'Test Episode',
            'description': 'Test description',
            'duration': 1800
        })
        
        with patch('upload_s3.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('upload_s3.S3Uploader') as mock_uploader_class:
            
            mock_args.return_value = Mock(
                mp3_file=temporary_mp3_file,
                s3_key='test/episode.mp3',
                bucket='test-bucket',
                max_retries=3,
                metadata=metadata_json
            )
            
            mock_uploader = Mock()
            mock_uploader_class.return_value = mock_uploader
            mock_uploader.check_bucket_exists.return_value = True
            mock_uploader.upload_with_retry.return_value = {
                'success': True,
                'url': 'https://test-bucket.s3.amazonaws.com/test/episode.mp3',
                'upload_duration': 1.5,
                'attempts': 1,
                'file_size': 1000
            }
            
            from upload_s3 import main
            main()
            
            # Verify metadata was passed to upload_with_retry
            upload_call_args = mock_uploader.upload_with_retry.call_args
            passed_metadata = upload_call_args[1]['metadata']
            assert passed_metadata['title'] == 'Test Episode'
            assert passed_metadata['description'] == 'Test description'
            assert passed_metadata['duration'] == '1800'  # Should be converted to string
    
    def test_main_with_invalid_metadata_json(self, temporary_mp3_file):
        """Test main function with invalid metadata JSON."""
        # Create test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'0' * 1000)
        
        with patch('upload_s3.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value = Mock(
                mp3_file=temporary_mp3_file,
                s3_key='test/episode.mp3',
                bucket='test-bucket',
                max_retries=3,
                metadata='invalid json'
            )
            
            with patch('upload_s3.sys.exit') as mock_exit:
                from upload_s3 import main
                main()
                mock_exit.assert_called_with(1)


class TestRetryLogic:
    """Comprehensive tests for retry logic behavior."""
    
    def test_retry_with_different_error_types(self, temporary_mp3_file):
        """Test retry behavior with different types of errors."""
        with patch('upload_s3.boto3.client') as mock_boto3, \
             patch('upload_s3.time.sleep') as mock_sleep:
            
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # Test different error scenarios
            error_scenarios = [
                # Transient errors that should be retried
                ClientError({'Error': {'Code': 'ServiceUnavailable'}}, 'PutObject'),
                ClientError({'Error': {'Code': 'InternalError'}}, 'PutObject'),
                ClientError({'Error': {'Code': 'SlowDown'}}, 'PutObject'),
                Exception("Network timeout"),
                
                # Should eventually succeed
                None
            ]
            
            mock_client.upload_file.side_effect = error_scenarios
            mock_client.head_object.return_value = {'ContentLength': 1000}
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=5
            )
            
            assert result['success'] is True
            assert result['attempts'] == 5
            
            # Verify all attempts were made
            assert mock_client.upload_file.call_count == 5
    
    def test_retry_respects_max_attempts(self, temporary_mp3_file):
        """Test that retry logic respects max_retries parameter."""
        with patch('upload_s3.boto3.client') as mock_boto3, \
             patch('upload_s3.time.sleep') as mock_sleep:
            
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # Always fail
            mock_client.upload_file.side_effect = Exception("Always fails")
            
            uploader = S3Uploader("test-bucket")
            
            # Create test file
            with open(temporary_mp3_file, 'wb') as f:
                f.write(b'0' * 1000)
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="test/episode.mp3",
                max_retries=2  # Only 2 retries
            )
            
            assert result['success'] is False
            assert result['attempts'] == 2
            
            # Verify only 2 attempts were made
            assert mock_client.upload_file.call_count == 2
            # Verify only 1 sleep (between first and second attempt)
            assert mock_sleep.call_count == 1


class TestIntegration:
    """Integration tests for S3 upload functionality."""
    
    @pytest.mark.integration 
    def test_complete_upload_workflow(self, temporary_mp3_file):
        """Test complete upload workflow with realistic file."""
        # Create a larger test file
        with open(temporary_mp3_file, 'wb') as f:
            f.write(b'ID3\x03\x00\x00\x00' + b'0' * 100000)  # ~100KB file
        
        with patch('upload_s3.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # Mock successful operations
            mock_client.head_bucket.return_value = None
            mock_client.upload_file.return_value = None
            mock_client.head_object.return_value = {'ContentLength': 100004}
            mock_client.get_bucket_location.return_value = {'LocationConstraint': 'us-west-2'}
            
            uploader = S3Uploader("integration-test-bucket", "us-west-2")
            
            # Check bucket exists
            assert uploader.check_bucket_exists() is True
            
            # Get bucket region
            assert uploader.get_bucket_region() == 'us-west-2'
            
            # Upload file with metadata
            metadata = {
                'episode_title': 'Integration Test Episode',
                'episode_description': 'This is an integration test',
                'duration_seconds': '3600',
                'created_by': 'automated-test'
            }
            
            result = uploader.upload_with_retry(
                local_file=temporary_mp3_file,
                s3_key="podcast/2025/integration-test.mp3",
                max_retries=3,
                metadata=metadata
            )
            
            # Verify successful upload
            assert result['success'] is True
            assert result['file_size'] == 100004
            assert result['attempts'] == 1
            assert result['url'] == "https://integration-test-bucket.s3.amazonaws.com/podcast/2025/integration-test.mp3"
            
            # Verify S3 operations were called correctly
            mock_client.head_bucket.assert_called_once()
            mock_client.upload_file.assert_called_once()
            mock_client.head_object.assert_called_once()
            
            # Verify upload parameters
            upload_call_args = mock_client.upload_file.call_args
            extra_args = upload_call_args[1]['ExtraArgs']
            assert extra_args['ContentType'] == 'audio/mpeg'
            assert extra_args['CacheControl'] == 'public, max-age=300'
            assert extra_args['ACL'] == 'public-read'
            assert extra_args['Metadata'] == metadata