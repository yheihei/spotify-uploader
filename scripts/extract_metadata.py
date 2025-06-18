#!/usr/bin/env python3
"""
Episode Metadata Extraction Script

This script extracts metadata from MP3 files including ID3 tags and file information.
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
    """MP3 metadata extraction utility"""
    
    def __init__(self, base_url: str, commit_sha: str):
        self.base_url = base_url.rstrip('/')
        self.commit_sha = commit_sha

    def extract_from_file(self, mp3_path: str) -> Dict[str, Any]:
        """Extract complete metadata from MP3 file"""
        
        if not os.path.exists(mp3_path):
            raise FileNotFoundError(f"MP3 file not found: {mp3_path}")
        
        # Extract slug from filename
        filename = os.path.basename(mp3_path)
        if not filename.endswith('.mp3'):
            raise ValueError(f"File is not an MP3: {filename}")
        
        slug = filename.replace('.mp3', '')
        
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
        file_size = os.path.getsize(mp3_path)
        
        # Load audio metadata
        try:
            audio_file = mutagen.File(mp3_path)
            if audio_file is None:
                raise ValueError(f"Could not read audio metadata from: {mp3_path}")
            
            # Extract basic info
            duration_seconds = int(audio_file.info.length) if audio_file.info else 0
            
            # Extract ID3 tags
            title = self._extract_title(audio_file, slug)
            description = self._extract_description(audio_file, slug)
            
        except (ID3NoHeaderError, Exception) as e:
            logger.warning(f"Could not read ID3 tags from {mp3_path}: {e}")
            # Fallback to filename-based metadata
            title = self._generate_title_from_slug(slug)
            description = f"Episode: {title}"
            duration_seconds = 0
        
        # Generate URLs and GUID
        year = pub_date.year
        s3_key = f"podcast/{year}/{slug}.mp3"
        mp3_url = f"{self.base_url}/{s3_key}"
        guid = f"repo-{self.commit_sha[:7]}-{slug}"
        
        # Prepare metadata
        metadata = {
            'slug': slug,
            'title': title,
            'description': description,
            'pub_date': pub_date.isoformat(),
            'duration_seconds': duration_seconds,
            'file_size_bytes': file_size,
            'mp3_url': mp3_url,
            'guid': guid,
            's3_key': s3_key,
            'year': year
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
        description='Extract metadata from MP3 episode file'
    )
    parser.add_argument(
        '--mp3-file',
        required=True,
        help='Path to MP3 file'
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
        
        # Extract metadata
        metadata = extractor.extract_from_file(args.mp3_file)
        
        # Output for GitHub Actions
        print(f"::set-output name=slug::{metadata['slug']}")
        print(f"::set-output name=title::{metadata['title']}")
        print(f"::set-output name=guid::{metadata['guid']}")
        print(f"::set-output name=metadata::{json.dumps(metadata)}")
        print(f"::set-output name=mp3-path::{args.mp3_file}")
        print(f"::set-output name=s3-key::{metadata['s3_key']}")
        print(f"::set-output name=commit-sha::{args.commit_sha}")
        
        # Log structured output
        logger.info(json.dumps({
            'event_type': 'metadata_extraction_complete',
            'episode_slug': metadata['slug'],
            'episode_title': metadata['title'],
            'episode_guid': metadata['guid'],
            'file_size_bytes': metadata['file_size_bytes'],
            'duration_seconds': metadata['duration_seconds']
        }))
        
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        print(f"::error title=Metadata Extraction Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()