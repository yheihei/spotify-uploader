#!/usr/bin/env python3
"""
RSS Feed Generator for Spotify Podcast Automation

This script generates RSS feeds for podcast episodes using the feedgen library.
It collects existing episodes from S3, generates a complete RSS feed, and 
deploys it atomically to S3.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from feedgen.feed import FeedGenerator


# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EpisodeMetadata:
    """Episode metadata container"""
    slug: str
    title: str
    description: str
    pub_date: datetime
    duration_seconds: int
    file_size_bytes: int
    mp3_url: str
    guid: str
    spotify_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'EpisodeMetadata':
        """Create EpisodeMetadata from dictionary"""
        return cls(
            slug=data['slug'],
            title=data['title'],
            description=data['description'],
            pub_date=datetime.fromisoformat(data['pub_date'].replace('Z', '+00:00')),
            duration_seconds=data['duration_seconds'],
            file_size_bytes=data['file_size_bytes'],
            mp3_url=data['mp3_url'],
            guid=data['guid'],
            spotify_url=data.get('spotify_url')
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'slug': self.slug,
            'title': self.title,
            'description': self.description,
            'pub_date': self.pub_date.isoformat(),
            'duration_seconds': self.duration_seconds,
            'file_size_bytes': self.file_size_bytes,
            'mp3_url': self.mp3_url,
            'guid': self.guid,
            'spotify_url': self.spotify_url
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


class RSSGenerator:
    """RSS Feed Generator with S3 integration"""
    
    def __init__(self, s3_client, bucket_name: str, base_url: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.base_url = base_url.rstrip('/')
        self.logger = StructuredLogger(__name__)
        
        # Podcast configuration
        self.podcast_config = {
            'title': os.getenv('PODCAST_TITLE', 'Your Podcast Title'),
            'description': os.getenv('PODCAST_DESCRIPTION', 'Your podcast description'),
            'author': os.getenv('PODCAST_AUTHOR', 'Your Name'),
            'email': os.getenv('PODCAST_EMAIL', 'your.email@example.com'),
            'language': os.getenv('PODCAST_LANGUAGE', 'ja'),
            'category': os.getenv('PODCAST_CATEGORY', 'Technology'),
            'subcategory': os.getenv('PODCAST_SUBCATEGORY', 'Software Engineering'),
            'explicit': os.getenv('PODCAST_EXPLICIT', 'false').lower() == 'true',
            'image_url': os.getenv('PODCAST_IMAGE_URL', f'{base_url}/podcast-cover.jpg')
        }

    def collect_existing_episodes(self) -> List[EpisodeMetadata]:
        """Collect existing episode information from S3"""
        self.logger.log_event('collecting_episodes_start', bucket=self.bucket_name)
        
        episodes = []
        
        try:
            # List all MP3 files in the podcast directory
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix='podcast/',
                Delimiter='/'
            )
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    key = obj['Key']
                    if not key.endswith('.mp3'):
                        continue
                    
                    # Extract slug from S3 key: podcast/2025/20250618-title.mp3
                    slug = key.split('/')[-1].replace('.mp3', '')
                    
                    # Try to get episode metadata from S3 metadata
                    try:
                        response = self.s3_client.head_object(
                            Bucket=self.bucket_name,
                            Key=key
                        )
                        
                        metadata = response.get('Metadata', {})
                        
                        episode = EpisodeMetadata(
                            slug=slug,
                            title=metadata.get('title', slug.replace('-', ' ').title()),
                            description=metadata.get('description', f'Episode: {slug}'),
                            pub_date=self._parse_date_from_slug(slug),
                            duration_seconds=int(metadata.get('duration', '0') or '0'),
                            file_size_bytes=obj['Size'],
                            mp3_url=f"{self.base_url}/{key}",
                            guid=metadata.get('guid', f'episode-{slug}'),
                            spotify_url=metadata.get('spotify_url')
                        )
                        
                        episodes.append(episode)
                        
                    except ClientError as e:
                        self.logger.log_event(
                            'episode_metadata_error',
                            slug=slug,
                            error=str(e)
                        )
                        continue
            
            # Sort episodes by publication date (newest first)
            episodes.sort(key=lambda x: x.pub_date, reverse=True)
            
            self.logger.log_event(
                'collecting_episodes_complete',
                episode_count=len(episodes)
            )
            
            return episodes
            
        except ClientError as e:
            self.logger.log_event(
                'collecting_episodes_error',
                error=str(e),
                error_code=e.response['Error']['Code']
            )
            raise

    def _parse_date_from_slug(self, slug: str) -> datetime:
        """Extract publication date from episode slug"""
        try:
            # Assume slug starts with YYYYMMDD
            date_str = slug[:8]
            return datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            # Fallback to current date if parsing fails
            return datetime.now(timezone.utc)

    def _seconds_to_duration(self, seconds: int) -> str:
        """Convert seconds to HH:MM:SS format"""
        if seconds <= 0:
            return "00:00:00"
            
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def generate_rss(self, episodes: List[EpisodeMetadata], new_episode: Optional[EpisodeMetadata] = None) -> str:
        """Generate RSS feed XML from episodes"""
        self.logger.log_event('rss_generation_start', episode_count=len(episodes))
        
        # Add new episode if provided and not already in list
        if new_episode and not any(ep.guid == new_episode.guid for ep in episodes):
            episodes.insert(0, new_episode)  # Add at beginning (newest first)
            episodes.sort(key=lambda x: x.pub_date, reverse=True)
        
        try:
            fg = FeedGenerator()
            
            # Feed basic information
            fg.title(self.podcast_config['title'])
            fg.description(self.podcast_config['description'])
            fg.link(href=self.base_url)
            fg.language(self.podcast_config['language'])
            fg.lastBuildDate(datetime.now(timezone.utc))
            fg.generator('Spotify Podcast Automation v1.0')
            fg.managingEditor(self.podcast_config['email'])
            fg.webMaster(self.podcast_config['email'])
            
            # Podcast-specific iTunes tags
            fg.podcast.itunes_author(self.podcast_config['author'])
            fg.podcast.itunes_category(
                self.podcast_config['category'],
                self.podcast_config.get('subcategory')
            )
            fg.podcast.itunes_explicit(self.podcast_config['explicit'])
            fg.podcast.itunes_summary(self.podcast_config['description'])
            fg.podcast.itunes_owner(
                self.podcast_config['author'],
                self.podcast_config['email']
            )
            
            # Podcast cover image
            if self.podcast_config['image_url']:
                fg.image(
                    url=self.podcast_config['image_url'],
                    title=self.podcast_config['title'],
                    link=self.base_url
                )
                fg.podcast.itunes_image(self.podcast_config['image_url'])
            
            # Add episodes
            for episode in episodes:
                fe = fg.add_entry()
                fe.title(episode.title)
                fe.description(episode.description)
                fe.guid(episode.guid)
                fe.pubDate(episode.pub_date)
                fe.link(href=episode.mp3_url)
                
                # Enclosure (audio file)
                fe.enclosure(
                    url=episode.mp3_url,
                    length=str(episode.file_size_bytes),
                    type='audio/mpeg'
                )
                
                # iTunes-specific tags
                if episode.duration_seconds > 0:
                    fe.podcast.itunes_duration(
                        self._seconds_to_duration(episode.duration_seconds)
                    )
                fe.podcast.itunes_explicit(False)
                fe.podcast.itunes_summary(episode.description)
            
            # Generate RSS XML
            rss_xml = fg.rss_str(pretty=True).decode('utf-8')
            
            self.logger.log_event(
                'rss_generation_complete',
                episode_count=len(episodes),
                rss_size_bytes=len(rss_xml.encode('utf-8'))
            )
            
            return rss_xml
            
        except Exception as e:
            self.logger.log_event(
                'rss_generation_error',
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def deploy_rss_atomic(self, rss_content: str) -> str:
        """Deploy RSS feed atomically to S3"""
        temp_key = 'rss.xml.new'
        final_key = 'rss.xml'
        rss_url = f"{self.base_url}/{final_key}"
        
        self.logger.log_event('rss_deploy_start', temp_key=temp_key, final_key=final_key)
        
        try:
            # Step 1: Upload to temporary file
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=temp_key,
                Body=rss_content.encode('utf-8'),
                ContentType='application/rss+xml; charset=utf-8',
                CacheControl='public, max-age=300',
                ACL='public-read',
                Metadata={
                    'generated_at': datetime.utcnow().isoformat(),
                    'generator': 'spotify-uploader-automation'
                }
            )
            
            self.logger.log_event('rss_temp_upload_complete', key=temp_key)
            
            # Step 2: Atomic move (copy then delete)
            self.s3_client.copy_object(
                CopySource={'Bucket': self.bucket_name, 'Key': temp_key},
                Bucket=self.bucket_name,
                Key=final_key,
                MetadataDirective='COPY',
                ACL='public-read'
            )
            
            self.logger.log_event('rss_copy_complete', final_key=final_key)
            
            # Step 3: Delete temporary file
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=temp_key
            )
            
            self.logger.log_event('rss_temp_cleanup_complete', temp_key=temp_key)
            
            # Verify deployment
            try:
                response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=final_key
                )
                
                self.logger.log_event(
                    'rss_deploy_complete',
                    rss_url=rss_url,
                    size_bytes=response['ContentLength'],
                    last_modified=response['LastModified'].isoformat()
                )
                
                return rss_url
                
            except ClientError as e:
                self.logger.log_event(
                    'rss_deploy_verification_failed',
                    error=str(e)
                )
                raise
                
        except ClientError as e:
            self.logger.log_event(
                'rss_deploy_error',
                error=str(e),
                error_code=e.response['Error']['Code']
            )
            
            # Cleanup temporary file if it exists
            try:
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=temp_key
                )
            except ClientError:
                pass  # Ignore cleanup errors
                
            raise

    def update_episode_metadata(self, episode: EpisodeMetadata):
        """Update episode metadata in S3 object metadata"""
        year = episode.pub_date.year
        s3_key = f"podcast/{year}/{episode.slug}.mp3"
        
        try:
            # Get current object
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            # Update metadata
            new_metadata = {
                'title': episode.title,
                'description': episode.description,
                'duration': str(episode.duration_seconds),
                'guid': episode.guid,
                'pub_date': episode.pub_date.isoformat()
            }
            
            if episode.spotify_url:
                new_metadata['spotify_url'] = episode.spotify_url
            
            # Copy object with new metadata
            self.s3_client.copy_object(
                CopySource={'Bucket': self.bucket_name, 'Key': s3_key},
                Bucket=self.bucket_name,
                Key=s3_key,
                Metadata=new_metadata,
                MetadataDirective='REPLACE',
                ACL='public-read'
            )
            
            self.logger.log_event(
                'episode_metadata_updated',
                slug=episode.slug,
                s3_key=s3_key
            )
            
        except ClientError as e:
            self.logger.log_event(
                'episode_metadata_update_error',
                slug=episode.slug,
                error=str(e)
            )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate and deploy RSS feed for podcast episodes'
    )
    parser.add_argument(
        '--bucket',
        required=True,
        help='S3 bucket name'
    )
    parser.add_argument(
        '--base-url',
        required=True,
        help='Base URL for podcast files'
    )
    parser.add_argument(
        '--episode-metadata',
        help='JSON metadata for new episode (optional)'
    )
    parser.add_argument(
        '--commit-sha',
        help='Git commit SHA for GUID generation'
    )
    
    args = parser.parse_args()
    
    # Initialize S3 client
    try:
        s3_client = boto3.client('s3')
    except NoCredentialsError:
        logger.error("AWS credentials not found")
        sys.exit(1)
    
    # Initialize RSS generator
    rss_generator = RSSGenerator(s3_client, args.bucket, args.base_url)
    
    try:
        # Collect existing episodes
        existing_episodes = rss_generator.collect_existing_episodes()
        
        # Parse new episode metadata if provided
        new_episode = None
        if args.episode_metadata:
            try:
                episode_data = json.loads(args.episode_metadata)
                new_episode = EpisodeMetadata.from_dict(episode_data)
                
                # Update episode metadata in S3
                rss_generator.update_episode_metadata(new_episode)
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Invalid episode metadata: {e}")
                sys.exit(1)
        
        # Generate RSS feed
        rss_content = rss_generator.generate_rss(existing_episodes, new_episode)
        
        # Deploy atomically
        rss_url = rss_generator.deploy_rss_atomic(rss_content)
        
        # Output for GitHub Actions
        print(f"::set-output name=rss-url::{rss_url}")
        print(f"::set-output name=duration::{datetime.utcnow().isoformat()}")
        
        logger.info(f"RSS feed successfully deployed to {rss_url}")
        
    except Exception as e:
        logger.error(f"RSS generation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()