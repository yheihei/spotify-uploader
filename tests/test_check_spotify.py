"""
Tests for Spotify verification script (check_spotify.py).

This module tests the Spotify episode verification functionality including:
- OAuth authentication with refresh tokens
- Episode search and verification
- Polling logic with retry attempts
- Error handling and API response processing
"""

import json
import pytest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import requests

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from check_spotify import SpotifyVerifier, VerificationResult


class TestVerificationResult:
    """Test cases for VerificationResult class."""
    
    def test_verification_result_creation_success(self):
        """Test creating successful VerificationResult."""
        result = VerificationResult(
            success=True,
            episode_guid="repo-abc123-20250618-test",
            attempts_made=3,
            time_taken_seconds=90,
            spotify_episode_id="spotify123",
            spotify_url="https://open.spotify.com/episode/spotify123"
        )
        
        assert result.success is True
        assert result.episode_guid == "repo-abc123-20250618-test"
        assert result.attempts_made == 3
        assert result.time_taken_seconds == 90
        assert result.spotify_episode_id == "spotify123"
        assert result.spotify_url == "https://open.spotify.com/episode/spotify123"
        assert result.error_message is None
    
    def test_verification_result_creation_failure(self):
        """Test creating failed VerificationResult."""
        result = VerificationResult(
            success=False,
            episode_guid="repo-abc123-20250618-test",
            attempts_made=10,
            time_taken_seconds=300,
            error_message="Episode not found after 10 attempts"
        )
        
        assert result.success is False
        assert result.episode_guid == "repo-abc123-20250618-test"
        assert result.attempts_made == 10
        assert result.time_taken_seconds == 300
        assert result.spotify_episode_id is None
        assert result.spotify_url is None
        assert result.error_message == "Episode not found after 10 attempts"
    
    def test_verification_result_to_dict(self):
        """Test converting VerificationResult to dictionary."""
        result = VerificationResult(
            success=True,
            episode_guid="test-guid",
            attempts_made=2,
            time_taken_seconds=60,
            spotify_episode_id="ep123",
            spotify_url="https://open.spotify.com/episode/ep123"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['success'] is True
        assert result_dict['episode_guid'] == "test-guid"
        assert result_dict['attempts_made'] == 2
        assert result_dict['time_taken_seconds'] == 60
        assert result_dict['spotify_episode_id'] == "ep123"
        assert result_dict['spotify_url'] == "https://open.spotify.com/episode/ep123"
        assert result_dict['error_message'] is None
    
    def test_verification_result_to_summary(self):
        """Test converting VerificationResult to summary format."""
        result = VerificationResult(
            success=True,
            episode_guid="test-guid",
            attempts_made=2,
            time_taken_seconds=60,
            spotify_url="https://open.spotify.com/episode/ep123"
        )
        
        summary = result.to_summary()
        
        assert summary['status'] == '✅ 成功'
        assert summary['guid'] == "test-guid"
        assert summary['attempts'] == 2
        assert summary['duration'] == "60秒"
        assert summary['spotify_url'] == "https://open.spotify.com/episode/ep123"
        assert summary['error'] == 'なし'
    
    def test_verification_result_to_summary_failure(self):
        """Test converting failed VerificationResult to summary format."""
        result = VerificationResult(
            success=False,
            episode_guid="test-guid",
            attempts_made=10,
            time_taken_seconds=300,
            error_message="Not found"
        )
        
        summary = result.to_summary()
        
        assert summary['status'] == '❌ 失敗'
        assert summary['spotify_url'] == 'N/A'
        assert summary['error'] == 'Not found'


class TestSpotifyVerifier:
    """Test cases for SpotifyVerifier class."""
    
    @pytest.fixture
    def verifier(self):
        """Create SpotifyVerifier instance for testing."""
        return SpotifyVerifier(
            client_id="test_client_id",
            client_secret="test_client_secret",
            refresh_token="test_refresh_token"
        )
    
    def test_verifier_initialization(self, verifier):
        """Test SpotifyVerifier initialization."""
        assert verifier.client_id == "test_client_id"
        assert verifier.client_secret == "test_client_secret"
        assert verifier.refresh_token == "test_refresh_token"
        assert verifier.access_token is None
        assert verifier.token_expires_at is None
        assert verifier.auth_url == 'https://accounts.spotify.com/api/token'
        assert verifier.api_base_url == 'https://api.spotify.com/v1'
        assert hasattr(verifier, 'session')
    
    @patch('check_spotify.datetime')
    def test_authenticate_success(self, mock_datetime, verifier):
        """Test successful authentication."""
        # Mock current time
        mock_datetime.now.return_value.timestamp.return_value = 1000000
        mock_datetime.utcnow.return_value.isoformat.return_value = '2025-06-18T10:00:00'
        
        # Mock successful auth response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'new_access_token',
            'expires_in': 3600
        }
        
        verifier.session.post = Mock(return_value=mock_response)
        
        result = verifier.authenticate()
        
        assert result is True
        assert verifier.access_token == 'new_access_token'
        assert verifier.token_expires_at == 1000000 + 3600
        
        # Verify API call
        verifier.session.post.assert_called_once_with(
            'https://accounts.spotify.com/api/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': 'test_refresh_token',
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
    
    def test_authenticate_failure(self, verifier):
        """Test authentication failure."""
        # Mock failed auth response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            'error': 'invalid_grant',
            'error_description': 'Invalid refresh token'
        }
        
        verifier.session.post = Mock(return_value=mock_response)
        
        result = verifier.authenticate()
        
        assert result is False
        assert verifier.access_token is None
    
    def test_authenticate_network_error(self, verifier):
        """Test authentication with network error."""
        verifier.session.post = Mock(side_effect=requests.RequestException("Network error"))
        
        result = verifier.authenticate()
        
        assert result is False
        assert verifier.access_token is None
    
    @patch('check_spotify.datetime')
    def test_ensure_valid_token_no_token(self, mock_datetime, verifier):
        """Test ensuring valid token when no token exists."""
        mock_datetime.now.return_value.timestamp.return_value = 1000000
        mock_datetime.utcnow.return_value.isoformat.return_value = '2025-06-18T10:00:00'
        
        # Mock successful authentication
        with patch.object(verifier, 'authenticate', return_value=True) as mock_auth:
            result = verifier._ensure_valid_token()
            
            assert result is True
            mock_auth.assert_called_once()
    
    @patch('check_spotify.datetime')
    def test_ensure_valid_token_expired(self, mock_datetime, verifier):
        """Test ensuring valid token when token is expired."""
        current_time = 1000000
        mock_datetime.now.return_value.timestamp.return_value = current_time
        mock_datetime.utcnow.return_value.isoformat.return_value = '2025-06-18T10:00:00'
        
        # Set expired token
        verifier.access_token = "expired_token"
        verifier.token_expires_at = current_time - 100  # Expired
        
        with patch.object(verifier, 'authenticate', return_value=True) as mock_auth:
            result = verifier._ensure_valid_token()
            
            assert result is True
            mock_auth.assert_called_once()
    
    @patch('check_spotify.datetime')
    def test_ensure_valid_token_valid(self, mock_datetime, verifier):
        """Test ensuring valid token when token is still valid."""
        current_time = 1000000
        mock_datetime.now.return_value.timestamp.return_value = current_time
        mock_datetime.utcnow.return_value.isoformat.return_value = '2025-06-18T10:00:00'
        
        # Set valid token (expires in 10 minutes)
        verifier.access_token = "valid_token"
        verifier.token_expires_at = current_time + 600
        
        with patch.object(verifier, 'authenticate') as mock_auth:
            result = verifier._ensure_valid_token()
            
            assert result is True
            mock_auth.assert_not_called()
    
    def test_get_show_episodes_success(self, verifier):
        """Test successful get_show_episodes call."""
        # Setup valid token
        verifier.access_token = "valid_token"
        verifier.token_expires_at = time.time() + 3600
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'id': 'episode1',
                    'name': 'Test Episode 1',
                    'description': 'Description 1'
                },
                {
                    'id': 'episode2',
                    'name': 'Test Episode 2', 
                    'description': 'Description 2'
                }
            ],
            'next': None
        }
        
        verifier.session.get = Mock(return_value=mock_response)
        
        result = verifier.get_show_episodes("show123", limit=50, offset=0)
        
        assert result is not None
        assert len(result['items']) == 2
        assert result['items'][0]['id'] == 'episode1'
        
        # Verify API call
        verifier.session.get.assert_called_once()
        call_args = verifier.session.get.call_args
        assert 'shows/show123/episodes' in call_args[0][0]
        assert call_args[1]['params']['limit'] == 50
        assert call_args[1]['params']['offset'] == 0
        assert call_args[1]['params']['market'] == 'US'
    
    def test_get_show_episodes_unauthorized_retry(self, verifier):
        """Test get_show_episodes with 401 error and retry."""
        verifier.access_token = "initial_token"
        verifier.token_expires_at = time.time() + 3600
        
        # First call returns 401, second call succeeds
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'items': []}
        
        verifier.session.get = Mock(side_effect=[mock_response_401, mock_response_200])
        
        with patch.object(verifier, 'authenticate', return_value=True) as mock_auth:
            result = verifier.get_show_episodes("show123")
            
            assert result is not None
            assert result['items'] == []
            mock_auth.assert_called_once()
            assert verifier.session.get.call_count == 2
    
    def test_get_show_episodes_error(self, verifier):
        """Test get_show_episodes with API error."""
        verifier.access_token = "valid_token"
        verifier.token_expires_at = time.time() + 3600
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        
        verifier.session.get = Mock(return_value=mock_response)
        
        result = verifier.get_show_episodes("show123")
        
        assert result is None
    
    def test_get_show_episodes_network_error(self, verifier):
        """Test get_show_episodes with network error."""
        verifier.access_token = "valid_token"
        verifier.token_expires_at = time.time() + 3600
        
        verifier.session.get = Mock(side_effect=requests.RequestException("Network error"))
        
        result = verifier.get_show_episodes("show123")
        
        assert result is None
    
    def test_find_episode_by_guid_found(self, verifier):
        """Test finding episode by GUID successfully."""
        target_guid = "repo-abc123-20250618-test"
        
        # Mock API response with matching episode
        episodes_data = {
            'items': [
                {
                    'id': 'episode1',
                    'name': 'Test Episode',
                    'description': f'This episode contains GUID: {target_guid}'
                }
            ],
            'next': None
        }
        
        with patch.object(verifier, 'get_show_episodes', return_value=episodes_data):
            result = verifier.find_episode_by_guid("show123", target_guid)
            
            assert result is not None
            assert result['id'] == 'episode1'
            assert result['name'] == 'Test Episode'
    
    def test_find_episode_by_guid_not_found(self, verifier):
        """Test finding episode by GUID when not found."""
        target_guid = "repo-abc123-20250618-missing"
        
        # Mock API response without matching episode
        episodes_data = {
            'items': [
                {
                    'id': 'episode1',
                    'name': 'Different Episode',
                    'description': 'Different description'
                }
            ],
            'next': None
        }
        
        with patch.object(verifier, 'get_show_episodes', return_value=episodes_data):
            result = verifier.find_episode_by_guid("show123", target_guid)
            
            assert result is None
    
    def test_find_episode_by_guid_multiple_pages(self, verifier):
        """Test finding episode by GUID across multiple pages."""
        target_guid = "repo-abc123-20250618-test"
        
        # Mock paginated API responses
        page1_data = {
            'items': [{'id': 'episode1', 'name': 'Episode 1', 'description': 'Description 1'}],
            'next': 'next_page_url'
        }
        
        page2_data = {
            'items': [
                {
                    'id': 'episode2',
                    'name': 'Episode 2',
                    'description': f'Contains target GUID: {target_guid}'
                }
            ],
            'next': None
        }
        
        with patch.object(verifier, 'get_show_episodes', side_effect=[page1_data, page2_data]):
            result = verifier.find_episode_by_guid("show123", target_guid)
            
            assert result is not None
            assert result['id'] == 'episode2'
    
    def test_find_episode_by_guid_api_error(self, verifier):
        """Test finding episode by GUID with API error."""
        target_guid = "repo-abc123-20250618-test"
        
        with patch.object(verifier, 'get_show_episodes', return_value=None):
            result = verifier.find_episode_by_guid("show123", target_guid)
            
            assert result is None
    
    def test_find_episode_by_guid_safety_limit(self, verifier):
        """Test finding episode by GUID respects safety limit."""
        target_guid = "repo-abc123-20250618-test"
        
        # Mock response that always has more pages
        episodes_data = {
            'items': [{'id': 'episode1', 'name': 'Episode 1', 'description': 'No match'}],
            'next': 'always_has_next'
        }
        
        with patch.object(verifier, 'get_show_episodes', return_value=episodes_data):
            result = verifier.find_episode_by_guid("show123", target_guid)
            
            assert result is None
            # Should have stopped at safety limit (1000 episodes / 50 per page = 20 calls)
            assert verifier.get_show_episodes.call_count <= 20
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_verify_episode_with_polling_success(self, mock_time, mock_sleep, verifier):
        """Test successful episode verification with polling."""
        mock_time.side_effect = [0, 30]  # Start, after second attempt
        
        target_guid = "repo-abc123-20250618-test"
        
        # Mock episode found on second attempt
        mock_episode = {
            'id': 'episode123',
            'name': 'Test Episode',
            'external_urls': {'spotify': 'https://open.spotify.com/episode/episode123'}
        }
        
        with patch.object(verifier, 'find_episode_by_guid', side_effect=[None, mock_episode]):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=10,
                poll_interval=30
            )
            
            assert result.success is True
            assert result.episode_guid == target_guid
            assert result.attempts_made == 2
            assert result.time_taken_seconds == 30
            assert result.spotify_episode_id == 'episode123'
            assert result.spotify_url == 'https://open.spotify.com/episode/episode123'
            
            # Verify sleep was called between attempts
            mock_sleep.assert_called_once_with(30)
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_verify_episode_with_polling_failure(self, mock_time, mock_sleep, verifier):
        """Test episode verification failure after all attempts."""
        mock_time.side_effect = [0, 300]  # Start, after all attempts
        
        target_guid = "repo-abc123-20250618-missing"
        
        # Episode never found
        with patch.object(verifier, 'find_episode_by_guid', return_value=None):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=10,
                poll_interval=30
            )
            
            assert result.success is False
            assert result.episode_guid == target_guid
            assert result.attempts_made == 10
            assert result.time_taken_seconds == 300
            assert result.spotify_episode_id is None
            assert result.spotify_url is None
            assert "Episode not found after 10 attempts" in result.error_message
            
            # Verify sleep was called 9 times (between 10 attempts)
            assert mock_sleep.call_count == 9
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_verify_episode_with_polling_first_attempt_success(self, mock_time, mock_sleep, verifier):
        """Test episode verification success on first attempt."""
        mock_time.side_effect = [0, 5]  # Start and quick end
        
        target_guid = "repo-abc123-20250618-test"
        
        # Episode found immediately
        mock_episode = {
            'id': 'episode123',
            'name': 'Test Episode',
            'external_urls': {'spotify': 'https://open.spotify.com/episode/episode123'}
        }
        
        with patch.object(verifier, 'find_episode_by_guid', return_value=mock_episode):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=10,
                poll_interval=30
            )
            
            assert result.success is True
            assert result.attempts_made == 1
            assert result.time_taken_seconds == 5
            
            # No sleep should be called for first attempt success
            mock_sleep.assert_not_called()
    
    def test_get_show_info_success(self, verifier):
        """Test successful show info retrieval."""
        verifier.access_token = "valid_token"
        verifier.token_expires_at = time.time() + 3600
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'show123',
            'name': 'Test Podcast',
            'description': 'Test podcast description'
        }
        
        verifier.session.get = Mock(return_value=mock_response)
        
        result = verifier.get_show_info("show123")
        
        assert result is not None
        assert result['id'] == 'show123'
        assert result['name'] == 'Test Podcast'
        
        # Verify API call
        verifier.session.get.assert_called_once()
        call_args = verifier.session.get.call_args
        assert 'shows/show123' in call_args[0][0]
    
    def test_get_show_info_error(self, verifier):
        """Test show info retrieval with error."""
        verifier.access_token = "valid_token"
        verifier.token_expires_at = time.time() + 3600
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 404
        
        verifier.session.get = Mock(return_value=mock_response)
        
        result = verifier.get_show_info("nonexistent_show")
        
        assert result is None


class TestMainFunction:
    """Test cases for main function."""
    
    def test_main_with_valid_args_success(self):
        """Test main function with valid arguments and successful verification."""
        with patch('check_spotify.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('check_spotify.SpotifyVerifier') as mock_verifier_class:
            
            mock_args.return_value = Mock(
                episode_guid='repo-abc123-20250618-test',
                show_id='show123',
                client_id='client123',
                client_secret='secret123',
                refresh_token='refresh123',
                max_attempts=10,
                poll_interval=30
            )
            
            mock_verifier = Mock()
            mock_verifier_class.return_value = mock_verifier
            
            # Mock successful show validation
            mock_verifier.get_show_info.return_value = {'name': 'Test Podcast'}
            
            # Mock successful verification
            mock_result = VerificationResult(
                success=True,
                episode_guid='repo-abc123-20250618-test',
                attempts_made=3,
                time_taken_seconds=90,
                spotify_episode_id='episode123',
                spotify_url='https://open.spotify.com/episode/episode123'
            )
            mock_verifier.verify_episode_with_polling.return_value = mock_result
            
            with patch('check_spotify.print') as mock_print:
                from check_spotify import main
                main()
                
                # Verify GitHub Actions outputs were printed
                output_calls = [str(call) for call in mock_print.call_args_list]
                assert any('::set-output name=status::success' in call for call in output_calls)
                assert any('::set-output name=spotify-url::' in call for call in output_calls)
                assert any('::set-output name=attempts::3' in call for call in output_calls)
                assert any('::set-output name=duration::90' in call for call in output_calls)
    
    def test_main_with_invalid_show_id(self):
        """Test main function with invalid show ID."""
        with patch('check_spotify.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('check_spotify.SpotifyVerifier') as mock_verifier_class:
            
            mock_args.return_value = Mock(
                episode_guid='repo-abc123-20250618-test',
                show_id='invalid_show',
                client_id='client123',
                client_secret='secret123',
                refresh_token='refresh123',
                max_attempts=10,
                poll_interval=30
            )
            
            mock_verifier = Mock()
            mock_verifier_class.return_value = mock_verifier
            
            # Mock failed show validation
            mock_verifier.get_show_info.return_value = None
            
            with patch('check_spotify.sys.exit') as mock_exit:
                from check_spotify import main
                main()
                mock_exit.assert_called_with(1)
    
    def test_main_with_verification_failure(self):
        """Test main function with verification failure."""
        with patch('check_spotify.argparse.ArgumentParser.parse_args') as mock_args, \
             patch('check_spotify.SpotifyVerifier') as mock_verifier_class:
            
            mock_args.return_value = Mock(
                episode_guid='repo-abc123-20250618-missing',
                show_id='show123',
                client_id='client123',
                client_secret='secret123',
                refresh_token='refresh123',
                max_attempts=10,
                poll_interval=30
            )
            
            mock_verifier = Mock()
            mock_verifier_class.return_value = mock_verifier
            
            # Mock successful show validation
            mock_verifier.get_show_info.return_value = {'name': 'Test Podcast'}
            
            # Mock failed verification
            mock_result = VerificationResult(
                success=False,
                episode_guid='repo-abc123-20250618-missing',
                attempts_made=10,
                time_taken_seconds=300,
                error_message='Episode not found after 10 attempts'
            )
            mock_verifier.verify_episode_with_polling.return_value = mock_result
            
            with patch('check_spotify.sys.exit') as mock_exit:
                from check_spotify import main
                main()
                mock_exit.assert_called_with(1)
    
    def test_main_with_exception(self):
        """Test main function with unexpected exception."""
        with patch('check_spotify.argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.side_effect = Exception("Unexpected error")
            
            with patch('check_spotify.sys.exit') as mock_exit, \
                 patch('check_spotify.print') as mock_print:
                from check_spotify import main
                main()
                
                mock_exit.assert_called_with(1)
                # Verify error output
                output_calls = [str(call) for call in mock_print.call_args_list]
                assert any('::set-output name=status::error' in call for call in output_calls)


class TestPollingBehavior:
    """Comprehensive tests for polling behavior."""
    
    @pytest.fixture
    def verifier(self):
        return SpotifyVerifier("client", "secret", "refresh")
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_polling_respects_max_attempts(self, mock_time, mock_sleep, verifier):
        """Test that polling respects max_attempts parameter."""
        mock_time.side_effect = list(range(0, 151, 15))  # 0, 15, 30, ..., 150
        
        target_guid = "repo-abc123-20250618-test"
        
        with patch.object(verifier, 'find_episode_by_guid', return_value=None):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=5,  # Only 5 attempts
                poll_interval=15
            )
            
            assert result.success is False
            assert result.attempts_made == 5
            
            # Verify correct number of sleep calls (4 sleeps between 5 attempts)
            assert mock_sleep.call_count == 4
            for call in mock_sleep.call_args_list:
                assert call[0][0] == 15  # poll_interval
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_polling_respects_poll_interval(self, mock_time, mock_sleep, verifier):
        """Test that polling respects poll_interval parameter."""
        mock_time.side_effect = list(range(0, 301, 45))  # 0, 45, 90, ..., 270
        
        target_guid = "repo-abc123-20250618-test"
        
        with patch.object(verifier, 'find_episode_by_guid', return_value=None):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=6,
                poll_interval=45  # Custom interval
            )
            
            assert result.success is False
            assert result.attempts_made == 6
            
            # Verify all sleep calls used correct interval
            for call in mock_sleep.call_args_list:
                assert call[0][0] == 45
    
    @patch('check_spotify.time.sleep')
    @patch('check_spotify.time.time')
    def test_polling_timing_accuracy(self, mock_time, mock_sleep, verifier):
        """Test that polling timing is calculated accurately."""
        # Mock time progression: start at 0, then 30s intervals
        time_progression = [0] + [30 * i for i in range(1, 6)]  # 0, 30, 60, 90, 120, 150
        mock_time.side_effect = time_progression
        
        target_guid = "repo-abc123-20250618-test"
        
        with patch.object(verifier, 'find_episode_by_guid', return_value=None):
            result = verifier.verify_episode_with_polling(
                show_id="show123",
                episode_guid=target_guid,
                max_attempts=5,
                poll_interval=30
            )
            
            # Should have taken exactly 30 seconds (time between start and second call)
            assert result.time_taken_seconds == 30
            assert result.attempts_made == 5


class TestIntegration:
    """Integration tests for Spotify verification."""
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_complete_verification_workflow_mock(self):
        """Test complete verification workflow with realistic mocking."""
        verifier = SpotifyVerifier(
            client_id="integration_client",
            client_secret="integration_secret", 
            refresh_token="integration_refresh"
        )
        
        # Mock the entire workflow
        with patch.object(verifier, 'session') as mock_session:
            # Mock authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {
                'access_token': 'integration_token',
                'expires_in': 3600
            }
            
            # Mock show info
            show_response = Mock()
            show_response.status_code = 200
            show_response.json.return_value = {
                'id': 'integration_show',
                'name': 'Integration Test Podcast'
            }
            
            # Mock episodes search - found on second attempt
            episodes_response_1 = Mock()
            episodes_response_1.status_code = 200
            episodes_response_1.json.return_value = {
                'items': [{'id': 'other_episode', 'name': 'Other', 'description': 'Other episode'}],
                'next': None
            }
            
            episodes_response_2 = Mock()
            episodes_response_2.status_code = 200
            episodes_response_2.json.return_value = {
                'items': [
                    {
                        'id': 'target_episode',
                        'name': 'Target Episode',
                        'description': 'Contains GUID: repo-abc123-20250618-integration-test',
                        'external_urls': {'spotify': 'https://open.spotify.com/episode/target_episode'}
                    }
                ],
                'next': None
            }
            
            # Setup mock responses in order
            mock_session.post.return_value = auth_response
            mock_session.get.side_effect = [show_response, episodes_response_1, episodes_response_2]
            
            # Run verification
            with patch('check_spotify.time.sleep'):  # Skip actual sleep
                result = verifier.verify_episode_with_polling(
                    show_id="integration_show",
                    episode_guid="repo-abc123-20250618-integration-test",
                    max_attempts=5,
                    poll_interval=10
                )
            
            # Verify successful result
            assert result.success is True
            assert result.episode_guid == "repo-abc123-20250618-integration-test"
            assert result.attempts_made == 3
            assert result.spotify_episode_id == 'target_episode'
            assert result.spotify_url == 'https://open.spotify.com/episode/target_episode'
            
            # Verify API calls were made correctly
            assert mock_session.post.call_count == 1  # Authentication
            assert mock_session.get.call_count == 3   # Show info + 2 episode searches