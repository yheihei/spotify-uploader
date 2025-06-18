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
    audio_url: str
    guid: str
    spotify_url: Optional[str] = None
    file_extension: Optional[str] = '.mp3'
    
    # iTunes拡張フィールド
    episode_image_url: Optional[str] = None
    season: Optional[int] = None
    episode_number: Optional[int] = None
    episode_type: Optional[str] = 'full'  # full/trailer/bonus
    itunes_summary: Optional[str] = None
    itunes_subtitle: Optional[str] = None
    itunes_keywords: Optional[List[str]] = None
    itunes_explicit: Optional[str] = 'no'  # yes/no/clean

    @classmethod
    def from_dict(cls, data: dict) -> 'EpisodeMetadata':
        """Create EpisodeMetadata from dictionary"""
        # Support both old mp3_url and new audio_url for backward compatibility
        audio_url = data.get('audio_url', data.get('mp3_url', ''))
        return cls(
            slug=data['slug'],
            title=data['title'],
            description=data['description'],
            pub_date=datetime.fromisoformat(data['pub_date'].replace('Z', '+00:00')),
            duration_seconds=data['duration_seconds'],
            file_size_bytes=data['file_size_bytes'],
            audio_url=audio_url,
            guid=data['guid'],
            spotify_url=data.get('spotify_url'),
            file_extension=data.get('file_extension', '.mp3'),
            # iTunes拡張フィールド
            episode_image_url=data.get('episode_image_url'),
            season=data.get('season'),
            episode_number=data.get('episode_number'),
            episode_type=data.get('episode_type', 'full'),
            itunes_summary=data.get('itunes_summary'),
            itunes_subtitle=data.get('itunes_subtitle'),
            itunes_keywords=data.get('itunes_keywords'),
            itunes_explicit=data.get('itunes_explicit', 'no')
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'slug': self.slug,
            'title': self.title,
            'description': self.description,
            'pub_date': self.pub_date.isoformat(),
            'duration_seconds': self.duration_seconds,
            'file_size_bytes': self.file_size_bytes,
            'audio_url': self.audio_url,
            'guid': self.guid,
            'spotify_url': self.spotify_url,
            'file_extension': self.file_extension
        }
        
        # iTunes拡張フィールド（値がある場合のみ追加）
        if self.episode_image_url:
            result['episode_image_url'] = self.episode_image_url
        if self.season is not None:
            result['season'] = self.season
        if self.episode_number is not None:
            result['episode_number'] = self.episode_number
        if self.episode_type:
            result['episode_type'] = self.episode_type
        if self.itunes_summary:
            result['itunes_summary'] = self.itunes_summary
        if self.itunes_subtitle:
            result['itunes_subtitle'] = self.itunes_subtitle
        if self.itunes_keywords:
            result['itunes_keywords'] = self.itunes_keywords
        if self.itunes_explicit:
            result['itunes_explicit'] = self.itunes_explicit
            
        return result
    
    @classmethod
    def from_episode_directory(cls, directory_path: str, base_url: str, commit_sha: str = '') -> 'EpisodeMetadata':
        """Create EpisodeMetadata from episode directory
        
        Args:
            directory_path: Path to episode directory containing audio file and episode_data.json
            base_url: Base URL for constructing file URLs
            commit_sha: Git commit SHA for GUID generation
        """
        import os
        import json
        import glob
        from mutagen import File as MutagenFile
        
        # ディレクトリ名からslugとpub_dateを推定
        dir_name = os.path.basename(directory_path)
        slug = dir_name
        
        # デフォルトのpub_date（YYYYMMDD形式から推定を試みる）
        pub_date = datetime.now(timezone.utc)
        if len(dir_name) >= 8:
            try:
                date_str = dir_name[:8]
                pub_date = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        
        # 音声ファイルを検出
        audio_files = glob.glob(os.path.join(directory_path, '*.mp3')) + \
                     glob.glob(os.path.join(directory_path, '*.wav'))
        
        if not audio_files:
            raise ValueError(f"No audio file found in {directory_path}")
        
        audio_file = audio_files[0]  # 最初の音声ファイルを使用
        file_extension = os.path.splitext(audio_file)[1]
        
        # 音声ファイルのメタデータを取得
        file_size_bytes = os.path.getsize(audio_file)
        duration_seconds = 0
        
        try:
            audio_metadata = MutagenFile(audio_file)
            if audio_metadata and hasattr(audio_metadata.info, 'length'):
                duration_seconds = int(audio_metadata.info.length)
        except Exception:
            pass
        
        # episode_data.jsonを読み込む
        json_path = os.path.join(directory_path, 'episode_data.json')
        episode_data = {}
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    episode_data = json.load(f)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse episode_data.json: {e}")
        
        # 必須フィールドのデフォルト値
        title = episode_data.get('title', slug.replace('-', ' ').title())
        description = episode_data.get('description', f'Episode: {slug}')
        
        # pub_dateの処理
        if 'pub_date' in episode_data:
            try:
                pub_date = datetime.fromisoformat(episode_data['pub_date'].replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # S3パスの生成
        year = pub_date.year
        audio_filename = os.path.basename(audio_file)
        s3_audio_key = f"podcast/{year}/{slug}/{audio_filename}"
        audio_url = f"{base_url.rstrip('/')}/{s3_audio_key}"
        
        # エピソード画像URLの処理
        episode_image_url = None
        if 'episode_image' in episode_data:
            image_filename = episode_data['episode_image']
            image_path = os.path.join(directory_path, image_filename)
            if os.path.exists(image_path):
                s3_image_key = f"podcast/{year}/{slug}/{image_filename}"
                episode_image_url = f"{base_url.rstrip('/')}/{s3_image_key}"
        
        # GUIDの生成
        guid = episode_data.get('guid', f"{commit_sha}-{slug}" if commit_sha else f"episode-{slug}")
        
        # EpisodeMetadataオブジェクトを作成
        return cls(
            slug=slug,
            title=title,
            description=description,
            pub_date=pub_date,
            duration_seconds=episode_data.get('duration_seconds', duration_seconds),
            file_size_bytes=file_size_bytes,
            audio_url=audio_url,
            guid=guid,
            spotify_url=episode_data.get('spotify_url'),
            file_extension=file_extension,
            # iTunes拡張フィールド
            episode_image_url=episode_image_url or episode_data.get('episode_image_url'),
            season=episode_data.get('season'),
            episode_number=episode_data.get('episode_number'),
            episode_type=episode_data.get('episode_type', 'full'),
            itunes_summary=episode_data.get('itunes_summary'),
            itunes_subtitle=episode_data.get('itunes_subtitle'),
            itunes_keywords=episode_data.get('itunes_keywords'),
            itunes_explicit=episode_data.get('itunes_explicit', 'no')
        )


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
            'explicit': 'yes' if os.getenv('PODCAST_EXPLICIT', 'false').lower() == 'true' else 'no',
            'image_url': os.getenv('PODCAST_IMAGE_URL', f'{base_url}/podcast-cover.jpg')
        }

    def collect_episode_directories(self, episodes_dir: str = 'episodes') -> List[EpisodeMetadata]:
        """Collect episodes from directory structure
        
        Args:
            episodes_dir: Path to the episodes directory
            
        Returns:
            List of EpisodeMetadata objects from directories
        """
        import os
        import glob
        
        self.logger.log_event('collecting_episode_directories_start', episodes_dir=episodes_dir)
        
        episodes = []
        
        if not os.path.exists(episodes_dir):
            self.logger.log_event('episodes_directory_not_found', episodes_dir=episodes_dir)
            return episodes
        
        # エピソードディレクトリをスキャン
        for item in sorted(os.listdir(episodes_dir)):
            item_path = os.path.join(episodes_dir, item)
            
            # ディレクトリの場合
            if os.path.isdir(item_path):
                try:
                    # ディレクトリから EpisodeMetadata を作成
                    episode = EpisodeMetadata.from_episode_directory(
                        item_path, 
                        self.base_url,
                        os.getenv('GITHUB_SHA', '')
                    )
                    episodes.append(episode)
                    
                    self.logger.log_event(
                        'episode_directory_processed',
                        slug=episode.slug,
                        title=episode.title
                    )
                    
                except Exception as e:
                    self.logger.log_event(
                        'episode_directory_error',
                        directory=item,
                        error=str(e)
                    )
                    continue
            
            # 直接音声ファイルの場合（後方互換性）
            elif item.endswith(('.mp3', '.wav')):
                self.logger.log_event(
                    'legacy_audio_file_found',
                    file=item,
                    message='Consider migrating to directory structure'
                )
        
        self.logger.log_event(
            'collecting_episode_directories_complete',
            episode_count=len(episodes)
        )
        
        return episodes
    
    def collect_existing_episodes(self) -> List[EpisodeMetadata]:
        """Collect existing episode information from S3"""
        self.logger.log_event('collecting_episodes_start', bucket=self.bucket_name)
        
        episodes = []
        
        try:
            # List all audio files in the podcast directory
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
                    if not (key.endswith('.mp3') or key.endswith('.wav')):
                        continue
                    
                    # Extract slug and file extension from S3 key: podcast/2025/20250618-title.mp3
                    filename = key.split('/')[-1]
                    if filename.endswith('.mp3'):
                        slug = filename.replace('.mp3', '')
                        file_extension = '.mp3'
                    else:  # WAV file
                        slug = filename.replace('.wav', '')
                        file_extension = '.wav'
                    
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
                            audio_url=f"{self.base_url}/{key}",
                            guid=metadata.get('guid', f'episode-{slug}'),
                            spotify_url=metadata.get('spotify_url'),
                            file_extension=file_extension,
                            # iTunes拡張フィールド（S3メタデータから取得可能な範囲で）
                            season=int(metadata.get('season', '0')) if metadata.get('season') else None,
                            episode_number=int(metadata.get('episode_number', '0')) if metadata.get('episode_number') else None,
                            episode_type=metadata.get('episode_type', 'full'),
                            itunes_explicit=metadata.get('itunes_explicit', 'no')
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
            fg.load_extension('podcast')
            
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
                fe.link(href=episode.audio_url)
                
                # Enclosure (audio file)
                # Determine MIME type based on file extension
                if episode.file_extension == '.wav':
                    mime_type = 'audio/wav'
                else:  # Default to MP3
                    mime_type = 'audio/mpeg'
                
                fe.enclosure(
                    url=episode.audio_url,
                    length=str(episode.file_size_bytes),
                    type=mime_type
                )
                
                # iTunes-specific tags
                if episode.duration_seconds > 0:
                    fe.podcast.itunes_duration(
                        self._seconds_to_duration(episode.duration_seconds)
                    )
                
                # エピソード固有のiTunesタグ
                fe.podcast.itunes_explicit(episode.itunes_explicit or 'no')
                fe.podcast.itunes_summary(episode.itunes_summary or episode.description)
                
                # 新しいiTunesタグ
                if episode.itunes_subtitle:
                    fe.podcast.itunes_subtitle(episode.itunes_subtitle)
                
                if episode.episode_image_url:
                    fe.podcast.itunes_image(episode.episode_image_url)
                
                if episode.season is not None:
                    fe.podcast.itunes_season(str(episode.season))
                
                if episode.episode_number is not None:
                    fe.podcast.itunes_episode(str(episode.episode_number))
                
                if episode.episode_type and episode.episode_type != 'full':
                    fe.podcast.itunes_episode_type(episode.episode_type)
                
                # iTunes keywords は feedgen がサポートしていないため、後でXML処理で追加
                # TODO: RSS生成後にXMLを直接編集してkeywordsタグを追加
            
            # Generate RSS XML
            rss_xml = fg.rss_str(pretty=True).decode('utf-8')
            
            # Post-process RSS to add iTunes keywords (not supported by feedgen)
            rss_xml = self._add_itunes_keywords(rss_xml, episodes)
            
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
    
    def _add_itunes_keywords(self, rss_xml: str, episodes: List[EpisodeMetadata]) -> str:
        """Add iTunes keywords to RSS XML (post-processing)
        
        Args:
            rss_xml: Generated RSS XML string
            episodes: List of episodes with keywords
            
        Returns:
            Modified RSS XML with iTunes keywords
        """
        import re
        
        # Create mapping of GUIDs to keywords
        guid_to_keywords = {}
        for episode in episodes:
            if episode.itunes_keywords:
                keywords_str = ','.join(episode.itunes_keywords)
                guid_to_keywords[episode.guid] = keywords_str
        
        if not guid_to_keywords:
            return rss_xml
        
        # Process each item in the RSS
        def add_keywords_to_item(match):
            item_xml = match.group(0)
            
            # Extract GUID from this item
            guid_match = re.search(r'<guid[^>]*>([^<]+)</guid>', item_xml)
            if not guid_match:
                return item_xml
                
            guid = guid_match.group(1)
            if guid not in guid_to_keywords:
                return item_xml
            
            keywords = guid_to_keywords[guid]
            
            # Insert keywords tag before </item>
            keywords_tag = f'    <itunes:keywords>{keywords}</itunes:keywords>\n  '
            item_xml = item_xml.replace('</item>', f'{keywords_tag}</item>')
            
            return item_xml
        
        # Apply to all items
        rss_xml = re.sub(r'<item>.*?</item>', add_keywords_to_item, rss_xml, flags=re.DOTALL)
        
        return rss_xml

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
        s3_key = f"podcast/{year}/{episode.slug}{episode.file_extension}"
        
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
        help='JSON metadata for new episode (optional, for legacy mode)'
    )
    parser.add_argument(
        '--commit-sha',
        help='Git commit SHA for GUID generation'
    )
    parser.add_argument(
        '--use-episode-directories',
        action='store_true',
        help='Use episode directory structure instead of S3-only episodes'
    )
    parser.add_argument(
        '--episodes-dir',
        default='episodes',
        help='Path to episodes directory (default: episodes)'
    )
    
    args = parser.parse_args()
    
    # Initialize S3 client
    s3_client = None
    try:
        s3_client = boto3.client('s3')
    except NoCredentialsError:
        logger.error("AWS credentials not found")
        sys.exit(1)
    
    # Initialize RSS generator
    rss_generator = RSSGenerator(s3_client, args.bucket, args.base_url)
    
    try:
        # Collect episodes based on mode
        if args.use_episode_directories:
            # Use directory-based episode collection
            episodes = rss_generator.collect_episode_directories(args.episodes_dir)
        else:
            # Use legacy S3-based episode collection
            episodes = rss_generator.collect_existing_episodes()
            
            # Parse new episode metadata if provided (legacy mode)
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
            
            # Add new episode to list for legacy mode
            if new_episode:
                episodes.insert(0, new_episode)
        
        # Generate RSS feed
        rss_content = rss_generator.generate_rss(episodes)
        
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