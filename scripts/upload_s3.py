#!/usr/bin/env python3
"""
S3 Upload Script

This script uploads audio files (MP3/WAV) to AWS S3 with retry logic and proper
metadata configuration for podcast distribution.
"""

import argparse
import json
import logging
import os
import sys
import time
import glob
from datetime import datetime
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class S3Uploader:
    """S3 upload utility with retry logic"""
    
    def __init__(self, bucket_name: str, region: str = None):
        self.bucket_name = bucket_name
        self.region = region
        
        try:
            if region:
                self.s3_client = boto3.client('s3', region_name=region)
            else:
                self.s3_client = boto3.client('s3')
        except NoCredentialsError:
            raise ValueError("AWS credentials not found")
        
        logger.info(f"Initialized S3 uploader for bucket: {bucket_name}")

    def upload_with_retry(self, local_file: str, s3_key: str, 
                         max_retries: int = 3, 
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload file to S3 with retry logic"""
        
        if not os.path.exists(local_file):
            raise FileNotFoundError(f"Local file not found: {local_file}")
        
        file_size = os.path.getsize(local_file)
        
        logger.info(f"Starting upload: {local_file} -> s3://{self.bucket_name}/{s3_key}")
        logger.info(f"File size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        
        for attempt in range(1, max_retries + 1):
            start_time = time.time()
            
            try:
                logger.info(f"Upload attempt {attempt}/{max_retries}")
                
                # Prepare upload arguments
                # Determine content type based on file extension
                content_type = self._get_content_type(local_file)
                
                upload_args = {
                    'ContentType': content_type,
                    'CacheControl': 'public, max-age=300',
                    'ACL': 'public-read'
                }
                
                # Add custom metadata if provided
                if metadata:
                    upload_args['Metadata'] = metadata
                
                # Perform upload
                self.s3_client.upload_file(
                    local_file,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs=upload_args
                )
                
                upload_duration = time.time() - start_time
                
                # Verify upload
                if self._verify_upload(s3_key, file_size):
                    logger.info(f"✅ Upload successful in {upload_duration:.2f} seconds")
                    
                    # Return success result
                    return {
                        'success': True,
                        'bucket': self.bucket_name,
                        's3_key': s3_key,
                        'file_size': file_size,
                        'upload_duration': upload_duration,
                        'attempts': attempt,
                        'url': f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
                    }
                else:
                    raise Exception("Upload verification failed")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Upload attempt {attempt} failed: {error_msg}")
                
                if attempt == max_retries:
                    logger.error(f"❌ All {max_retries} upload attempts failed")
                    return {
                        'success': False,
                        'error': error_msg,
                        'attempts': attempt
                    }
                else:
                    # Exponential backoff
                    wait_time = 2 ** (attempt - 1)
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
        
        # This should never be reached, but just in case
        return {
            'success': False,
            'error': 'Unknown upload failure',
            'attempts': max_retries
        }

    def _verify_upload(self, s3_key: str, expected_size: int) -> bool:
        """Verify that upload was successful"""
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            actual_size = response['ContentLength']
            
            if actual_size != expected_size:
                logger.error(f"Size mismatch: expected {expected_size}, got {actual_size}")
                return False
            
            logger.info(f"Upload verified: {actual_size:,} bytes")
            return True
            
        except ClientError as e:
            logger.error(f"Verification failed: {e}")
            return False

    def update_object_metadata(self, s3_key: str, metadata: Dict[str, str]) -> bool:
        """Update object metadata without re-uploading"""
        try:
            # Copy object with new metadata
            copy_source = {'Bucket': self.bucket_name, 'Key': s3_key}
            
            # Determine content type based on file extension
            content_type = self._get_content_type(s3_key)
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=s3_key,
                Metadata=metadata,
                MetadataDirective='REPLACE',
                ACL='public-read',
                ContentType=content_type,
                CacheControl='public, max-age=300'
            )
            
            logger.info(f"Updated metadata for s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to update metadata: {e}")
            return False

    def check_bucket_exists(self) -> bool:
        """Check if the S3 bucket exists and is accessible"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✅ Bucket {self.bucket_name} is accessible")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"❌ Bucket {self.bucket_name} does not exist")
            elif error_code == '403':
                logger.error(f"❌ Access denied to bucket {self.bucket_name}")
            else:
                logger.error(f"❌ Error accessing bucket {self.bucket_name}: {error_code}")
            return False

    def get_bucket_region(self) -> Optional[str]:
        """Get the region of the S3 bucket"""
        try:
            response = self.s3_client.get_bucket_location(Bucket=self.bucket_name)
            region = response['LocationConstraint']
            
            # us-east-1 returns None in LocationConstraint
            if region is None:
                region = 'us-east-1'
            
            logger.info(f"Bucket region: {region}")
            return region
            
        except ClientError as e:
            logger.warning(f"Could not determine bucket region: {e}")
            return None
    
    def _get_content_type(self, file_path: str) -> str:
        """Determine content type based on file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        
        content_types = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.json': 'application/json'
        }
        
        return content_types.get(ext, 'application/octet-stream')
    
    def upload_episode_directory(self, episode_dir: str, base_s3_path: str, 
                                episode_metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload entire episode directory to S3
        
        Args:
            episode_dir: Path to episode directory containing audio and other files
            base_s3_path: Base S3 path (e.g., 'podcast/2025/episode-slug')
            episode_metadata: Metadata to attach to audio files
            
        Returns:
            Dictionary with upload results for all files
        """
        if not os.path.exists(episode_dir):
            raise FileNotFoundError(f"Episode directory not found: {episode_dir}")
        
        if not os.path.isdir(episode_dir):
            raise ValueError(f"Path is not a directory: {episode_dir}")
        
        logger.info(f"Starting episode directory upload: {episode_dir}")
        logger.info(f"S3 base path: s3://{self.bucket_name}/{base_s3_path}")
        
        results = {
            'success': True,
            'files': {},
            'audio_file': None,
            'episode_image': None,
            'total_files': 0,
            'failed_files': 0
        }
        
        # Find all files in the directory
        all_files = []
        for file_path in glob.glob(os.path.join(episode_dir, '*')):
            if os.path.isfile(file_path):
                all_files.append(file_path)
        
        if not all_files:
            logger.warning(f"No files found in directory: {episode_dir}")
            return results
        
        results['total_files'] = len(all_files)
        
        # Upload each file
        for file_path in all_files:
            filename = os.path.basename(file_path)
            s3_key = f"{base_s3_path}/{filename}"
            
            try:
                # Prepare metadata
                file_metadata = {}
                
                # Add episode metadata to audio files
                if filename.endswith(('.mp3', '.wav')) and episode_metadata:
                    file_metadata.update(episode_metadata)
                
                # Upload file
                result = self.upload_with_retry(
                    local_file=file_path,
                    s3_key=s3_key,
                    metadata=file_metadata if file_metadata else None
                )
                
                if result['success']:
                    results['files'][filename] = result
                    
                    # Track special files
                    if filename.endswith(('.mp3', '.wav')):
                        results['audio_file'] = {
                            'filename': filename,
                            's3_key': s3_key,
                            'url': result['url']
                        }
                    elif filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        results['episode_image'] = {
                            'filename': filename,
                            's3_key': s3_key,
                            'url': result['url']
                        }
                    
                    logger.info(f"✅ Uploaded: {filename}")
                else:
                    results['failed_files'] += 1
                    results['files'][filename] = result
                    results['success'] = False
                    logger.error(f"❌ Failed to upload: {filename}")
                    
            except Exception as e:
                results['failed_files'] += 1
                results['files'][filename] = {
                    'success': False,
                    'error': str(e)
                }
                results['success'] = False
                logger.error(f"❌ Error uploading {filename}: {e}")
        
        # Summary
        successful_files = results['total_files'] - results['failed_files']
        logger.info(f"Directory upload complete: {successful_files}/{results['total_files']} files successful")
        
        if results['audio_file']:
            logger.info(f"📻 Audio file: {results['audio_file']['url']}")
        if results['episode_image']:
            logger.info(f"🖼️  Episode image: {results['episode_image']['url']}")
        
        return results
    
    def generate_episode_s3_path(self, episode_slug: str, pub_date: datetime) -> str:
        """Generate S3 path for episode based on slug and publication date
        
        Args:
            episode_slug: Episode slug (e.g., '20250618-test-episode')
            pub_date: Publication date
            
        Returns:
            S3 path (e.g., 'podcast/2025/20250618-test-episode')
        """
        year = pub_date.year
        return f"podcast/{year}/{episode_slug}"


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Upload audio file or episode directory to S3 with retry logic'
    )
    
    # Create mutually exclusive group for single file vs directory upload
    upload_group = parser.add_mutually_exclusive_group(required=True)
    upload_group.add_argument(
        '--audio-file',
        help='Path to audio file (MP3 or WAV) to upload'
    )
    upload_group.add_argument(
        '--episode-dir',
        help='Path to episode directory containing audio and other files'
    )
    
    parser.add_argument(
        '--s3-key',
        help='S3 key (path) for the uploaded file (required for --audio-file)'
    )
    parser.add_argument(
        '--s3-base-path',
        help='Base S3 path for episode directory (e.g., podcast/2025/episode-slug)'
    )
    parser.add_argument(
        '--bucket',
        required=True,
        help='S3 bucket name'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=3,
        help='Maximum number of retry attempts (default: 3)'
    )
    parser.add_argument(
        '--metadata',
        help='JSON string of metadata to attach to the S3 object'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.audio_file and not args.s3_key:
        parser.error("--s3-key is required when using --audio-file")
    
    if args.episode_dir and not args.s3_base_path:
        parser.error("--s3-base-path is required when using --episode-dir")
    
    try:
        # Parse metadata if provided
        metadata = None
        if args.metadata:
            try:
                metadata = json.loads(args.metadata)
                # Ensure all values are strings (S3 metadata requirement)
                metadata = {k: str(v) for k, v in metadata.items()}
            except json.JSONDecodeError as e:
                logger.error(f"Invalid metadata JSON: {e}")
                sys.exit(1)
        
        # Initialize uploader
        uploader = S3Uploader(args.bucket)
        
        # Check bucket accessibility
        if not uploader.check_bucket_exists():
            sys.exit(1)
        
        # Perform upload based on mode
        if args.audio_file:
            # Single file upload mode
            result = uploader.upload_with_retry(
                local_file=args.audio_file,
                s3_key=args.s3_key,
                max_retries=args.max_retries,
                metadata=metadata
            )
            
            if result['success']:
                # Output for GitHub Actions
                print(f"::set-output name=audio-url::{result['url']}")
                print(f"::set-output name=duration::{result['upload_duration']:.2f}")
                print(f"::set-output name=attempts::{result['attempts']}")
                print(f"::set-output name=file-size::{result['file_size']}")
                
                # Log structured output
                logger.info(json.dumps({
                    'event_type': 's3_upload_complete',
                    's3_key': args.s3_key,
                    'file_size_bytes': result['file_size'],
                    'upload_duration_seconds': result['upload_duration'],
                    'attempts': result['attempts'],
                    'url': result['url']
                }))
                
                logger.info(f"✅ Upload completed successfully: {result['url']}")
            else:
                logger.error(f"❌ Upload failed: {result['error']}")
                print(f"::error title=S3 Upload Failed::{result['error']}")
                sys.exit(1)
                
        elif args.episode_dir:
            # Episode directory upload mode
            result = uploader.upload_episode_directory(
                episode_dir=args.episode_dir,
                base_s3_path=args.s3_base_path,
                episode_metadata=metadata
            )
            
            if result['success']:
                # Output for GitHub Actions
                if result['audio_file']:
                    print(f"::set-output name=audio-url::{result['audio_file']['url']}")
                    print(f"::set-output name=audio-s3-key::{result['audio_file']['s3_key']}")
                
                if result['episode_image']:
                    print(f"::set-output name=episode-image-url::{result['episode_image']['url']}")
                    print(f"::set-output name=episode-image-s3-key::{result['episode_image']['s3_key']}")
                
                print(f"::set-output name=total-files::{result['total_files']}")
                print(f"::set-output name=failed-files::{result['failed_files']}")
                
                # Log structured output
                logger.info(json.dumps({
                    'event_type': 'episode_directory_upload_complete',
                    'episode_dir': args.episode_dir,
                    's3_base_path': args.s3_base_path,
                    'total_files': result['total_files'],
                    'failed_files': result['failed_files'],
                    'audio_file': result['audio_file'],
                    'episode_image': result['episode_image']
                }))
                
                logger.info(f"✅ Episode directory upload completed successfully")
            else:
                logger.error(f"❌ Episode directory upload failed")
                print(f"::error title=Episode Directory Upload Failed::Failed to upload {result['failed_files']} files")
                sys.exit(1)
            
    except Exception as e:
        logger.error(f"Upload process failed: {e}")
        print(f"::error title=Upload Process Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()