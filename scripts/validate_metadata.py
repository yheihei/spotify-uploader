#!/usr/bin/env python3
"""
Episode Metadata Validation Script

This script validates episode metadata to ensure it meets requirements
before processing in the podcast automation pipeline.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, List


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class MetadataValidator:
    """Episode metadata validation utility"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, metadata: Dict[str, Any]) -> bool:
        """Validate episode metadata"""
        
        logger.info("Starting metadata validation...")
        
        # Reset validation state
        self.errors = []
        self.warnings = []
        
        # Required fields validation
        self._validate_required_fields(metadata)
        
        # Field format validation
        self._validate_slug_format(metadata.get('slug'))
        self._validate_title(metadata.get('title'))
        self._validate_description(metadata.get('description'))
        self._validate_pub_date(metadata.get('pub_date'))
        self._validate_duration(metadata.get('duration_seconds'))
        self._validate_file_size(metadata.get('file_size_bytes'))
        self._validate_urls(metadata.get('audio_url'), metadata.get('guid'))
        self._validate_s3_key(metadata.get('s3_key'))
        
        # Log results
        if self.errors:
            logger.error(f"Validation failed with {len(self.errors)} errors:")
            for error in self.errors:
                logger.error(f"  ❌ {error}")
        
        if self.warnings:
            logger.warning(f"Validation completed with {len(self.warnings)} warnings:")
            for warning in self.warnings:
                logger.warning(f"  ⚠️ {warning}")
        
        if not self.errors and not self.warnings:
            logger.info("✅ Metadata validation passed with no issues")
        elif not self.errors:
            logger.info("✅ Metadata validation passed with warnings")
        
        return len(self.errors) == 0

    def _validate_required_fields(self, metadata: Dict[str, Any]):
        """Validate required fields are present"""
        required_fields = [
            'slug', 'title', 'description', 'pub_date',
            'duration_seconds', 'file_size_bytes', 'audio_url',
            'guid', 's3_key'
        ]
        
        for field in required_fields:
            if field not in metadata:
                self.errors.append(f"Missing required field: {field}")
            elif metadata[field] is None:
                self.errors.append(f"Required field is null: {field}")

    def _validate_slug_format(self, slug: str):
        """Validate slug format"""
        if not slug:
            return  # Already caught by required fields check
        
        # Check length
        if len(slug) < 11:  # YYYYMMDD-xx minimum
            self.errors.append(f"Slug too short: {slug}")
            return
        
        # Check date part
        date_part = slug[:8]
        if not date_part.isdigit():
            self.errors.append(f"Slug date part is not numeric: {date_part}")
            return
        
        # Validate date
        try:
            datetime.strptime(date_part, '%Y%m%d')
        except ValueError:
            self.errors.append(f"Invalid date in slug: {date_part}")
            return
        
        # Check separator
        if slug[8] != '-':
            self.errors.append(f"Missing separator after date in slug: {slug}")
            return
        
        # Check title part
        title_part = slug[9:]
        if not title_part:
            self.errors.append("Slug missing title part after date")
            return
        
        # Validate kebab-case format
        if not self._is_valid_kebab_case(title_part):
            self.errors.append(f"Slug title part is not valid kebab-case: {title_part}")

    def _is_valid_kebab_case(self, text: str) -> bool:
        """Check if text is valid kebab-case"""
        if not text:
            return False
        
        # Should only contain lowercase letters, numbers, and hyphens
        if not all(c.islower() or c.isdigit() or c == '-' for c in text):
            return False
        
        # Shouldn't start or end with hyphen
        if text.startswith('-') or text.endswith('-'):
            return False
        
        # No consecutive hyphens
        if '--' in text:
            return False
        
        return True

    def _validate_title(self, title: str):
        """Validate episode title"""
        if not title:
            return  # Already caught by required fields check
        
        # Check length
        if len(title) < 3:
            self.errors.append(f"Title too short: {title}")
        elif len(title) > 255:
            self.errors.append(f"Title too long ({len(title)} chars, max 255)")
        
        # Check for reasonable content
        if title.strip() != title:
            self.warnings.append("Title has leading or trailing whitespace")
        
        # Check for all caps (often indicates poor formatting)
        if title.isupper() and len(title) > 10:
            self.warnings.append("Title is all uppercase, consider proper case")

    def _validate_description(self, description: str):
        """Validate episode description"""
        if not description:
            return  # Already caught by required fields check
        
        # Check length
        if len(description) < 10:
            self.warnings.append(f"Description is quite short: {len(description)} chars")
        elif len(description) > 4000:
            self.warnings.append(f"Description is very long ({len(description)} chars)")
        
        # Check for whitespace issues
        if description.strip() != description:
            self.warnings.append("Description has leading or trailing whitespace")

    def _validate_pub_date(self, pub_date: str):
        """Validate publication date"""
        if not pub_date:
            return  # Already caught by required fields check
        
        # Check for complete ISO 8601 format (require time component)
        if 'T' not in pub_date:
            self.errors.append(f"Publication date must include time component: {pub_date}")
            return
            
        try:
            parsed_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            
            # Check if date is reasonable (not too far in future/past)
            now = datetime.now(parsed_date.tzinfo)
            
            # Check if more than 1 day in the future
            if (parsed_date - now).days > 1:
                self.warnings.append(f"Publication date is in the future: {pub_date}")
            
            # Check if more than 10 years in the past
            if (now - parsed_date).days > 3650:
                self.warnings.append(f"Publication date is very old: {pub_date}")
                
        except ValueError as e:
            self.errors.append(f"Invalid publication date format: {pub_date} ({e})")

    def _validate_duration(self, duration_seconds):
        """Validate episode duration"""
        if duration_seconds is None:
            return  # Already caught by required fields check
        
        if not isinstance(duration_seconds, int):
            try:
                duration_seconds = int(duration_seconds)
            except (ValueError, TypeError):
                self.errors.append(f"Duration is not a valid integer: {duration_seconds}")
                return
        
        # Check reasonable bounds
        if duration_seconds < 0:
            self.errors.append(f"Duration cannot be negative: {duration_seconds}")
        elif duration_seconds == 0:
            self.warnings.append("Duration is 0 seconds (metadata may be missing)")
        elif duration_seconds < 60:
            self.warnings.append(f"Episode is very short: {duration_seconds} seconds")
        elif duration_seconds > 14400:  # 4 hours
            self.warnings.append(f"Episode is very long: {duration_seconds/3600:.1f} hours")

    def _validate_file_size(self, file_size_bytes):
        """Validate file size"""
        if file_size_bytes is None:
            return  # Already caught by required fields check
        
        if not isinstance(file_size_bytes, int):
            try:
                file_size_bytes = int(file_size_bytes)
            except (ValueError, TypeError):
                self.errors.append(f"File size is not a valid integer: {file_size_bytes}")
                return
        
        # Check reasonable bounds
        if file_size_bytes <= 0:
            self.errors.append(f"File size must be positive: {file_size_bytes}")
        elif file_size_bytes < 1024 * 1024:  # 1MB
            self.warnings.append(f"File size is very small: {file_size_bytes/1024:.1f} KB")
        elif file_size_bytes > 500 * 1024 * 1024:  # 500MB
            self.warnings.append(f"File size is very large: {file_size_bytes/(1024*1024):.1f} MB")

    def _validate_urls(self, audio_url: str, guid: str):
        """Validate URLs and GUID"""
        if audio_url:
            if not audio_url.startswith(('http://', 'https://')):
                self.errors.append(f"Audio URL must start with http:// or https://: {audio_url}")
            elif not (audio_url.endswith('.mp3') or audio_url.endswith('.wav')):
                self.errors.append(f"Audio URL must end with .mp3 or .wav: {audio_url}")
            elif ' ' in audio_url:
                self.errors.append(f"Audio URL contains spaces: {audio_url}")
        
        if guid:
            # GUID should follow repo-{sha}-{slug} format
            if not guid.startswith('repo-'):
                self.errors.append(f"GUID should start with 'repo-': {guid}")
            
            parts = guid.split('-', 2)
            if len(parts) < 3:
                self.errors.append(f"GUID should have format 'repo-{{sha}}-{{slug}}': {guid}")
            elif len(parts[1]) != 7:
                self.warnings.append(f"GUID SHA part should be 7 characters: {parts[1]}")

    def _validate_s3_key(self, s3_key: str):
        """Validate S3 key format"""
        if not s3_key:
            return  # Already caught by required fields check
        
        # Should follow podcast/{YYYY}/{slug}.{mp3|wav} format
        if not s3_key.startswith('podcast/'):
            self.errors.append(f"S3 key should start with 'podcast/': {s3_key}")
            return
        
        if not (s3_key.endswith('.mp3') or s3_key.endswith('.wav')):
            self.errors.append(f"S3 key should end with '.mp3' or '.wav': {s3_key}")
            return
        
        # Check year part
        parts = s3_key.split('/')
        if len(parts) != 3:
            self.errors.append(f"S3 key should have format 'podcast/YYYY/slug.{{mp3|wav}}': {s3_key}")
            return
        
        year_part = parts[1]
        if not year_part.isdigit() or len(year_part) != 4:
            self.errors.append(f"Year in S3 key should be 4 digits: {year_part}")
        else:
            year = int(year_part)
            current_year = datetime.now().year
            if year < 2000 or year > current_year + 1:
                self.warnings.append(f"Year in S3 key seems unreasonable: {year}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Validate episode metadata'
    )
    parser.add_argument(
        '--metadata',
        required=True,
        help='JSON metadata to validate'
    )
    
    args = parser.parse_args()
    
    try:
        # Parse metadata
        metadata = json.loads(args.metadata)
        
        # Validate
        validator = MetadataValidator()
        is_valid = validator.validate(metadata)
        
        # Output validation results
        # Output errors for GitHub Actions
        for error in validator.errors:
            print(f"::error title=Validation Error::{error}")
        
        # Output warnings for GitHub Actions
        for warning in validator.warnings:
            print(f"::warning title=Validation Warning::{warning}")
        
        if is_valid:
            logger.info("✅ Metadata validation successful")
            sys.exit(0)
        else:
            logger.error("❌ Metadata validation failed")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON metadata: {e}")
        print(f"::error title=JSON Parse Error::{e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Validation process failed: {e}")
        print(f"::error title=Validation Process Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()