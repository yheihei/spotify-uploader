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
from datetime import datetime
from typing import Dict, Any, Optional

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
                if local_file.lower().endswith('.wav'):
                    content_type = 'audio/wav'
                else:  # Default to MP3
                    content_type = 'audio/mpeg'
                
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
            if s3_key.lower().endswith('.wav'):
                content_type = 'audio/wav'
            else:  # Default to MP3
                content_type = 'audio/mpeg'
            
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


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Upload audio file (MP3/WAV) to S3 with retry logic'
    )
    parser.add_argument(
        '--audio-file',
        required=True,
        help='Path to audio file (MP3 or WAV) to upload'
    )
    parser.add_argument(
        '--s3-key',
        required=True,
        help='S3 key (path) for the uploaded file'
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
        
        # Perform upload
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
            
    except Exception as e:
        logger.error(f"Upload process failed: {e}")
        print(f"::error title=Upload Process Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()