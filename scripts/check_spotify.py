#!/usr/bin/env python3
"""
Spotify Episode Verification Script

This script verifies that a podcast episode has been indexed by Spotify
by polling the Spotify Web API. It uses OAuth refresh token authentication
and implements retry logic with exponential backoff.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Spotify verification result container"""
    success: bool
    episode_guid: str
    attempts_made: int
    time_taken_seconds: int
    spotify_episode_id: Optional[str] = None
    spotify_url: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'success': self.success,
            'episode_guid': self.episode_guid,
            'attempts_made': self.attempts_made,
            'time_taken_seconds': self.time_taken_seconds,
            'spotify_episode_id': self.spotify_episode_id,
            'spotify_url': self.spotify_url,
            'error_message': self.error_message
        }
    
    def to_summary(self) -> dict:
        """Convert to GitHub Actions Summary format"""
        return {
            'status': '✅ 成功' if self.success else '❌ 失敗',
            'guid': self.episode_guid,
            'attempts': self.attempts_made,
            'duration': f"{self.time_taken_seconds}秒",
            'spotify_url': self.spotify_url or 'N/A',
            'error': self.error_message or 'なし'
        }


class StructuredLogger:
    """Structured JSON logger for GitHub Actions"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_event(self, event_type: str, **kwargs):
        """Log structured event"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            **kwargs
        }
        self.logger.info(json.dumps(log_entry))


class SpotifyVerifier:
    """Spotify episode verification client"""
    
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.logger = StructuredLogger(__name__)
        
        # Configure HTTP session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Spotify API endpoints
        self.auth_url = 'https://accounts.spotify.com/api/token'
        self.api_base_url = 'https://api.spotify.com/v1'

    def authenticate(self) -> bool:
        """Authenticate with Spotify using refresh token"""
        self.logger.log_event('spotify_auth_start')
        
        try:
            auth_data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = self.session.post(
                self.auth_url,
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = datetime.now(timezone.utc).timestamp() + expires_in
                
                self.logger.log_event(
                    'spotify_auth_success',
                    expires_in=expires_in
                )
                return True
            else:
                error_msg = f"Authentication failed: {response.status_code}"
                if response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        error_data = response.json()
                        error_msg += f" - {error_data.get('error_description', error_data.get('error', ''))}"
                    except json.JSONDecodeError:
                        pass
                
                self.logger.log_event(
                    'spotify_auth_failed',
                    status_code=response.status_code,
                    error=error_msg
                )
                return False
                
        except requests.RequestException as e:
            self.logger.log_event(
                'spotify_auth_error',
                error=str(e),
                error_type=type(e).__name__
            )
            return False

    def _ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token"""
        if not self.access_token:
            return self.authenticate()
        
        # Check if token is about to expire (with 5 minute buffer)
        if self.token_expires_at and datetime.now(timezone.utc).timestamp() > (self.token_expires_at - 300):
            return self.authenticate()
        
        return True

    def get_show_episodes(self, show_id: str, limit: int = 50, offset: int = 0) -> Optional[Dict[str, Any]]:
        """Get episodes for a specific show"""
        if not self._ensure_valid_token():
            return None
        
        try:
            url = f"{self.api_base_url}/shows/{show_id}/episodes"
            params = {
                'limit': min(limit, 50),  # Spotify API limit
                'offset': offset,
                'market': 'US'  # Required parameter
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Token expired, try to refresh once
                if self.authenticate():
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    response = self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30
                    )
                    if response.status_code == 200:
                        return response.json()
            
            self.logger.log_event(
                'spotify_api_error',
                endpoint='get_show_episodes',
                status_code=response.status_code,
                show_id=show_id
            )
            return None
            
        except requests.RequestException as e:
            self.logger.log_event(
                'spotify_api_request_error',
                endpoint='get_show_episodes',
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    def find_episode_by_guid(self, show_id: str, target_guid: str) -> Optional[Dict[str, Any]]:
        """Find episode by GUID across all episodes in the show"""
        self.logger.log_event(
            'episode_search_start',
            show_id=show_id,
            target_guid=target_guid
        )
        
        offset = 0
        limit = 50
        
        while True:
            episodes_data = self.get_show_episodes(show_id, limit, offset)
            
            if not episodes_data:
                self.logger.log_event(
                    'episode_search_api_failed',
                    offset=offset
                )
                return None
            
            episodes = episodes_data.get('items', [])
            
            if not episodes:
                self.logger.log_event(
                    'episode_search_no_more_episodes',
                    offset=offset
                )
                break
            
            # Search through episodes in this batch
            for episode in episodes:
                # Try to match by GUID from RSS description or name
                episode_name = episode.get('name', '')
                episode_description = episode.get('description', '')
                episode_id = episode.get('id', '')
                
                # Check if GUID appears in episode data
                if (target_guid in episode_name or 
                    target_guid in episode_description or
                    episode_id == target_guid):
                    
                    self.logger.log_event(
                        'episode_found',
                        episode_id=episode_id,
                        episode_name=episode_name,
                        target_guid=target_guid,
                        match_method='guid_match'
                    )
                    return episode
            
            # Check if there are more episodes
            if not episodes_data.get('next'):
                break
                
            offset += limit
            
            # Safety limit to prevent infinite loops
            if offset >= 1000:  # Max 1000 episodes to search
                self.logger.log_event(
                    'episode_search_limit_reached',
                    max_offset=offset
                )
                break
        
        self.logger.log_event(
            'episode_not_found',
            target_guid=target_guid,
            total_searched=offset + len(episodes)
        )
        return None

    def verify_episode_with_polling(self, show_id: str, episode_guid: str, 
                                   max_attempts: int = 10, 
                                   poll_interval: int = 30) -> VerificationResult:
        """Verify episode existence with polling"""
        
        start_time = time.time()
        
        self.logger.log_event(
            'verification_start',
            show_id=show_id,
            episode_guid=episode_guid,
            max_attempts=max_attempts,
            poll_interval=poll_interval
        )
        
        for attempt in range(1, max_attempts + 1):
            self.logger.log_event(
                'verification_attempt',
                attempt=attempt,
                max_attempts=max_attempts
            )
            
            episode = self.find_episode_by_guid(show_id, episode_guid)
            
            if episode:
                time_taken = int(time.time() - start_time)
                spotify_url = episode.get('external_urls', {}).get('spotify')
                
                result = VerificationResult(
                    success=True,
                    episode_guid=episode_guid,
                    attempts_made=attempt,
                    time_taken_seconds=time_taken,
                    spotify_episode_id=episode.get('id'),
                    spotify_url=spotify_url
                )
                
                self.logger.log_event(
                    'verification_success',
                    **result.to_dict()
                )
                
                return result
            
            # If not the last attempt, wait before retrying
            if attempt < max_attempts:
                self.logger.log_event(
                    'verification_waiting',
                    attempt=attempt,
                    wait_seconds=poll_interval
                )
                time.sleep(poll_interval)
        
        # All attempts exhausted
        time_taken = int(time.time() - start_time)
        result = VerificationResult(
            success=False,
            episode_guid=episode_guid,
            attempts_made=max_attempts,
            time_taken_seconds=time_taken,
            error_message=f"Episode not found after {max_attempts} attempts over {time_taken} seconds"
        )
        
        self.logger.log_event(
            'verification_failed',
            **result.to_dict()
        )
        
        return result

    def get_show_info(self, show_id: str) -> Optional[Dict[str, Any]]:
        """Get show information for validation"""
        if not self._ensure_valid_token():
            return None
        
        try:
            url = f"{self.api_base_url}/shows/{show_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.log_event(
                    'show_info_error',
                    status_code=response.status_code,
                    show_id=show_id
                )
                return None
                
        except requests.RequestException as e:
            self.logger.log_event(
                'show_info_request_error',
                error=str(e),
                show_id=show_id
            )
            return None


def main():
    """Main entry point"""
    try:
        parser = argparse.ArgumentParser(
            description='Verify podcast episode indexing on Spotify'
        )
        parser.add_argument(
            '--episode-guid',
            required=True,
            help='Episode GUID to verify'
        )
        parser.add_argument(
            '--show-id',
            required=True,
            help='Spotify show ID'
        )
        parser.add_argument(
            '--client-id',
            required=True,
            help='Spotify client ID'
        )
        parser.add_argument(
            '--client-secret',
            required=True,
            help='Spotify client secret'
        )
        parser.add_argument(
            '--refresh-token',
            required=True,
            help='Spotify refresh token'
        )
        parser.add_argument(
            '--max-attempts',
            type=int,
            default=10,
            help='Maximum polling attempts (default: 10)'
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=30,
            help='Polling interval in seconds (default: 30)'
        )
        
        args = parser.parse_args()
        
        # Initialize Spotify verifier
        verifier = SpotifyVerifier(
            client_id=args.client_id,
            client_secret=args.client_secret,
            refresh_token=args.refresh_token
        )
        
        # Validate show ID first
        show_info = verifier.get_show_info(args.show_id)
        if not show_info:
            logger.error(f"Could not validate show ID: {args.show_id}")
            sys.exit(1)
            return
        
        logger.info(f"Validating show: {show_info.get('name', 'Unknown')}")
        
        # Perform verification
        result = verifier.verify_episode_with_polling(
            show_id=args.show_id,
            episode_guid=args.episode_guid,
            max_attempts=args.max_attempts,
            poll_interval=args.poll_interval
        )
        
        # Output for GitHub Actions
        print(f"::set-output name=status::{'success' if result.success else 'failed'}")
        print(f"::set-output name=spotify-url::{result.spotify_url or ''}")
        print(f"::set-output name=attempts::{result.attempts_made}")
        print(f"::set-output name=duration::{result.time_taken_seconds}")
        
        if result.spotify_episode_id:
            print(f"::set-output name=episode-id::{result.spotify_episode_id}")
        
        # Summary output
        print(f"::notice title=Verification Result::{json.dumps(result.to_summary())}")
        
        if result.success:
            logger.info(f"✅ Episode verified successfully: {result.spotify_url}")
        else:
            logger.warning(f"❌ Episode verification failed: {result.error_message}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Verification process failed: {e}")
        print(f"::set-output name=status::error")
        print(f"::error title=Verification Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()