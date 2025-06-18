#!/usr/bin/env python3
"""
Episode Metadata Extraction Script

This script extracts metadata from audio files (MP3/WAV) including ID3 tags and file information.
It generates the episode GUID and prepares metadata for RSS generation.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import mutagen
from mutagen.id3 import ID3NoHeaderError


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Audio metadata extraction utility for MP3 and WAV files"""
    
    def __init__(self, base_url: str, commit_sha: str):
        self.base_url = base_url.rstrip('/')
        self.commit_sha = commit_sha

    def extract_from_directory(self, episode_dir: str) -> Dict[str, Any]:
        """Extract metadata from episode directory containing audio file and episode_data.json"""
        
        if not os.path.exists(episode_dir):
            raise FileNotFoundError(f"Episode directory not found: {episode_dir}")
        
        if not os.path.isdir(episode_dir):
            raise ValueError(f"Path is not a directory: {episode_dir}")
        
        # Get directory name as slug
        slug = os.path.basename(episode_dir)
        
        # Validate slug format
        if not self._validate_slug_format(slug):
            raise ValueError(f"Invalid slug format: {slug}. Expected: YYYYMMDD-title-kebab")
        
        # Extract date from slug
        try:
            date_str = slug[:8]
            pub_date = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Invalid date in slug: {slug[:8]}")
        
        # Find audio file in directory
        audio_files = []
        for filename in os.listdir(episode_dir):
            if filename.endswith(('.mp3', '.wav')):
                audio_files.append(os.path.join(episode_dir, filename))
        
        if not audio_files:
            raise ValueError(f"No audio files (MP3/WAV) found in directory: {episode_dir}")
        
        if len(audio_files) > 1:
            logger.warning(f"Multiple audio files found, using: {audio_files[0]}")
        
        audio_path = audio_files[0]
        file_extension = os.path.splitext(audio_path)[1]
        
        # Load episode_data.json if it exists
        episode_data_path = os.path.join(episode_dir, 'episode_data.json')
        episode_data = {}
        
        if os.path.exists(episode_data_path):
            try:
                with open(episode_data_path, 'r', encoding='utf-8') as f:
                    episode_data = json.load(f)
                logger.info(f"Loaded episode data from: {episode_data_path}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse episode_data.json: {e}")
        
        # Get file information
        file_size = os.path.getsize(audio_path)
        
        # Extract audio metadata
        duration_seconds = 0
        try:
            audio_file = mutagen.File(audio_path)
            if audio_file and audio_file.info:
                duration_seconds = int(audio_file.info.length)
        except Exception as e:
            logger.warning(f"Could not read audio metadata: {e}")
        
        # Use episode_data.json values or fall back to defaults
        title = episode_data.get('title', self._generate_title_from_slug(slug))
        description = episode_data.get('description', f'Episode: {title}')
        
        # Override duration if specified in episode_data.json
        if 'duration_seconds' in episode_data:
            duration_seconds = episode_data['duration_seconds']
        
        # Override pub_date if specified in episode_data.json
        if 'pub_date' in episode_data:
            try:
                pub_date = datetime.fromisoformat(episode_data['pub_date'].replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Invalid pub_date in episode_data.json, using slug date")
        
        # Generate URLs and paths
        year = pub_date.year
        s3_base_path = f"podcast/{year}/{slug}"
        audio_filename = os.path.basename(audio_path)
        s3_audio_key = f"{s3_base_path}/{audio_filename}"
        audio_url = f"{self.base_url}/{s3_audio_key}"
        
        # Generate GUID
        guid = episode_data.get('guid', f"repo-{self.commit_sha[:7]}-{slug}")
        
        # Find episode image if it exists
        episode_image_url = None
        if 'episode_image' in episode_data:
            image_filename = episode_data['episode_image']
            image_path = os.path.join(episode_dir, image_filename)
            if os.path.exists(image_path):
                s3_image_key = f"{s3_base_path}/{image_filename}"
                episode_image_url = f"{self.base_url}/{s3_image_key}"
        
        # Prepare complete metadata
        metadata = {
            'slug': slug,
            'title': title,
            'description': description,
            'pub_date': pub_date.isoformat(),
            'duration_seconds': duration_seconds,
            'file_size_bytes': file_size,
            'audio_url': audio_url,
            'guid': guid,
            's3_audio_key': s3_audio_key,
            's3_base_path': s3_base_path,
            'year': year,
            'file_extension': file_extension,
            'episode_directory': episode_dir,
            'audio_filename': audio_filename
        }
        
        # Add iTunes fields from episode_data.json
        itunes_fields = [
            'episode_image_url', 'season', 'episode_number', 'episode_type',
            'itunes_summary', 'itunes_subtitle', 'itunes_keywords', 'itunes_explicit'
        ]
        
        for field in itunes_fields:
            if field in episode_data:
                metadata[field] = episode_data[field]
        
        # Override episode_image_url if we found a local image
        if episode_image_url:
            metadata['episode_image_url'] = episode_image_url
        
        logger.info(f"Extracted metadata for episode directory: {slug}")
        logger.info(f"Title: {title}")
        logger.info(f"Duration: {duration_seconds}s")
        logger.info(f"File size: {file_size} bytes")
        logger.info(f"GUID: {guid}")
        if episode_image_url:
            logger.info(f"Episode image: {episode_image_url}")
        
        return metadata

    def extract_from_file(self, audio_path: str) -> Dict[str, Any]:
        """Extract complete metadata from audio file (MP3/WAV)"""
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Extract slug from filename
        filename = os.path.basename(audio_path)
        if not (filename.endswith('.mp3') or filename.endswith('.wav')):
            raise ValueError(f"File is not a supported audio format (MP3/WAV): {filename}")
        
        # Extract slug and file extension
        if filename.endswith('.mp3'):
            slug = filename.replace('.mp3', '')
            file_extension = '.mp3'
        else:  # WAV file
            slug = filename.replace('.wav', '')
            file_extension = '.wav'
        
        # Validate slug format (YYYYMMDD-title-kebab)
        if not self._validate_slug_format(slug):
            raise ValueError(f"Invalid slug format: {slug}. Expected: YYYYMMDD-title-kebab")
        
        # Extract date from slug
        try:
            date_str = slug[:8]
            pub_date = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Invalid date in slug: {slug[:8]}")
        
        # Get file information
        file_size = os.path.getsize(audio_path)
        
        # Load audio metadata
        try:
            audio_file = mutagen.File(audio_path)
            if audio_file is None:
                raise ValueError(f"Could not read audio metadata from: {audio_path}")
            
            # Extract basic info
            duration_seconds = int(audio_file.info.length) if audio_file.info else 0
            
            # Extract ID3 tags
            title = self._extract_title(audio_file, slug)
            description = self._extract_description(audio_file, slug)
            
        except (ID3NoHeaderError, Exception) as e:
            logger.warning(f"Could not read audio metadata from {audio_path}: {e}")
            # Fallback to filename-based metadata
            title = self._generate_title_from_slug(slug)
            description = f"Episode: {title}"
            duration_seconds = 0
        
        # Generate URLs and GUID
        year = pub_date.year
        s3_key = f"podcast/{year}/{slug}{file_extension}"
        audio_url = f"{self.base_url}/{s3_key}"
        guid = f"repo-{self.commit_sha[:7]}-{slug}"
        
        # Prepare metadata
        metadata = {
            'slug': slug,
            'title': title,
            'description': description,
            'pub_date': pub_date.isoformat(),
            'duration_seconds': duration_seconds,
            'file_size_bytes': file_size,
            'audio_url': audio_url,
            'guid': guid,
            's3_key': s3_key,
            'year': year,
            'file_extension': file_extension
        }
        
        logger.info(f"Extracted metadata for episode: {slug}")
        logger.info(f"Title: {title}")
        logger.info(f"Duration: {duration_seconds}s")
        logger.info(f"File size: {file_size} bytes")
        logger.info(f"GUID: {guid}")
        
        return metadata

    def _validate_slug_format(self, slug: str) -> bool:
        """Validate slug follows YYYYMMDD-title-kebab format"""
        if len(slug) < 9:  # At least YYYYMMDD-x
            return False
        
        # Check date part
        date_part = slug[:8]
        if not date_part.isdigit():
            return False
        
        # Validate date is actually a valid date
        try:
            parsed_date = datetime.strptime(date_part, '%Y%m%d')
            # Check reasonable year range (1900-2099)
            if not (1900 <= parsed_date.year <= 2099):
                return False
        except ValueError:
            return False
        
        # Check separator
        if slug[8] != '-':
            return False
        
        # Check remaining format (should be kebab-case)
        remaining = slug[9:]
        if not remaining or not all(c.islower() or c.isdigit() or c == '-' for c in remaining):
            return False
        
        # Shouldn't start or end with dash
        if remaining.startswith('-') or remaining.endswith('-'):
            return False
        
        # No double dashes
        if '--' in remaining:
            return False
        
        return True

    def _extract_title(self, audio_file, fallback_slug: str) -> str:
        """Extract title from ID3 tags"""
        # Try different title tags
        title_tags = ['TIT2', 'TITLE', 'Title']
        
        for tag in title_tags:
            if hasattr(audio_file, 'tags') and audio_file.tags:
                value = audio_file.tags.get(tag)
                if value:
                    if isinstance(value, list):
                        return str(value[0])
                    return str(value)
        
        # Fallback to generating from slug
        return self._generate_title_from_slug(fallback_slug)

    def _extract_description(self, audio_file, fallback_slug: str) -> str:
        """Extract description from ID3 tags"""
        # Try different description/comment tags
        desc_tags = ['COMM::eng', 'COMM', 'TALB', 'ALBUM', 'Album']
        
        for tag in desc_tags:
            if hasattr(audio_file, 'tags') and audio_file.tags:
                value = audio_file.tags.get(tag)
                if value:
                    if isinstance(value, list):
                        desc = str(value[0])
                    else:
                        desc = str(value)
                    
                    if desc and desc.strip():
                        return desc.strip()
        
        # Fallback to generating from slug
        title = self._generate_title_from_slug(fallback_slug)
        return f"Episode: {title}"

    def _generate_title_from_slug(self, slug: str) -> str:
        """Generate human-readable title from slug"""
        # Remove date prefix (YYYYMMDD-)
        if len(slug) > 9 and slug[8] == '-':
            title_part = slug[9:]
        else:
            title_part = slug
        
        # Convert kebab-case to Title Case
        words = title_part.split('-')
        title_words = [word.capitalize() for word in words if word]
        
        return ' '.join(title_words)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Extract metadata from audio episode file or episode directory'
    )
    
    # Create mutually exclusive group for file vs directory mode
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--audio-file',
        help='Path to audio file (MP3 or WAV)'
    )
    input_group.add_argument(
        '--episode-directory',
        help='Path to episode directory containing audio file and episode_data.json'
    )
    
    parser.add_argument(
        '--base-url',
        required=True,
        help='Base URL for generated URLs'
    )
    parser.add_argument(
        '--commit-sha',
        required=True,
        help='Git commit SHA for GUID generation'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize extractor
        extractor = MetadataExtractor(args.base_url, args.commit_sha)
        
        # Extract metadata based on mode
        if args.audio_file:
            # Single file mode (legacy)
            metadata = extractor.extract_from_file(args.audio_file)
            
            # Output for GitHub Actions (legacy format)
            print(f"::set-output name=slug::{metadata['slug']}")
            print(f"::set-output name=title::{metadata['title']}")
            print(f"::set-output name=guid::{metadata['guid']}")
            print(f"::set-output name=metadata::{json.dumps(metadata)}")
            print(f"::set-output name=audio-path::{args.audio_file}")
            print(f"::set-output name=s3-key::{metadata['s3_key']}")
            print(f"::set-output name=commit-sha::{args.commit_sha}")
            
        elif args.episode_directory:
            # Episode directory mode (new)
            metadata = extractor.extract_from_directory(args.episode_directory)
            
            # Output for GitHub Actions (new format)
            print(f"::set-output name=slug::{metadata['slug']}")
            print(f"::set-output name=title::{metadata['title']}")
            print(f"::set-output name=guid::{metadata['guid']}")
            print(f"::set-output name=metadata::{json.dumps(metadata)}")
            print(f"::set-output name=episode-directory::{metadata['episode_directory']}")
            print(f"::set-output name=s3-base-path::{metadata['s3_base_path']}")
            print(f"::set-output name=commit-sha::{args.commit_sha}")
        
        # Log structured output
        logger.info(json.dumps({
            'event_type': 'metadata_extraction_complete',
            'mode': 'directory' if args.episode_directory else 'file',
            'episode_slug': metadata['slug'],
            'episode_title': metadata['title'],
            'episode_guid': metadata['guid'],
            'file_size_bytes': metadata['file_size_bytes'],
            'duration_seconds': metadata['duration_seconds'],
            'itunes_fields': {k: v for k, v in metadata.items() 
                            if k.startswith('itunes_') or k in ['season', 'episode_number', 'episode_type']}
        }))
        
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        print(f"::error title=Metadata Extraction Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()