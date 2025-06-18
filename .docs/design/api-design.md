# API設計書

## 概要

本システムで使用する外部API、内部インターフェース、およびデータ交換仕様を定義します。

## 外部API統合

### 1. Spotify Web API

#### 認証エンドポイント
```http
POST https://accounts.spotify.com/api/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token={REFRESH_TOKEN}&
client_id={CLIENT_ID}&
client_secret={CLIENT_SECRET}
```

**レスポンス**:
```json
{
    "access_token": "NgCXRK...MzYjw",
    "token_type": "Bearer",
    "scope": "user-read-private",
    "expires_in": 3600
}
```

#### エピソード確認エンドポイント
```http
GET https://api.spotify.com/v1/shows/{show_id}/episodes?limit=50&offset=0
Authorization: Bearer {ACCESS_TOKEN}
```

**レスポンス**:
```json
{
    "href": "https://api.spotify.com/v1/shows/...",
    "items": [
        {
            "id": "4GI3dxEafwap1sFiTGPKd1",
            "name": "Episode Title",
            "description": "Episode description",
            "external_urls": {
                "spotify": "https://open.spotify.com/episode/..."
            },
            "release_date": "2025-06-18",
            "duration_ms": 3600000,
            "explicit": false,
            "uri": "spotify:episode:4GI3dxEafwap1sFiTGPKd1"
        }
    ],
    "limit": 50,
    "next": null,
    "offset": 0,
    "previous": null,
    "total": 1
}
```

#### レート制限対応
- **制限**: 100 requests/minute
- **対応**: 指数バックオフリトライ
- **ヘッダー監視**: `Retry-After`, `X-RateLimit-*`

### 2. AWS S3 API

#### ファイルアップロード
```python
s3_client.upload_file(
    Filename=local_file_path,
    Bucket=bucket_name,
    Key=s3_key,
    ExtraArgs={
        'ContentType': 'audio/mpeg',
        'CacheControl': 'public, max-age=300',
        'ACL': 'public-read'
    }
)
```

#### アトミックファイル操作
```python
# 1. 一時ファイルアップロード
s3_client.put_object(
    Bucket=bucket_name,
    Key='rss.xml.new',
    Body=rss_content,
    ContentType='application/rss+xml'
)

# 2. アトミック移動
s3_client.copy_object(
    CopySource={'Bucket': bucket_name, 'Key': 'rss.xml.new'},
    Bucket=bucket_name,
    Key='rss.xml'
)

# 3. 一時ファイル削除
s3_client.delete_object(Bucket=bucket_name, Key='rss.xml.new')
```

### 3. Slack Webhook API

#### 成功通知
```http
POST {SLACK_WEBHOOK_URL}
Content-Type: application/json

{
    "text": "✅ エピソード配信完了",
    "attachments": [
        {
            "color": "good",
            "fields": [
                {
                    "title": "エピソード",
                    "value": "20250618-automation-pipeline",
                    "short": true
                },
                {
                    "title": "Spotify URL",
                    "value": "https://open.spotify.com/episode/...",
                    "short": false
                },
                {
                    "title": "実行時間",
                    "value": "1分30秒",
                    "short": true
                }
            ]
        }
    ]
}
```

#### 失敗通知
```http
POST {SLACK_WEBHOOK_URL}
Content-Type: application/json

{
    "text": "❌ エピソード配信失敗",
    "attachments": [
        {
            "color": "danger",
            "fields": [
                {
                    "title": "エピソード", 
                    "value": "20250618-automation-pipeline",
                    "short": true
                },
                {
                    "title": "エラー詳細",
                    "value": "S3 upload failed: Connection timeout",
                    "short": false
                },
                {
                    "title": "GitHub Actions Run",
                    "value": "https://github.com/user/repo/actions/runs/123",
                    "short": false
                }
            ]
        }
    ]
}
```

## 内部インターフェース

### 1. エピソードメタデータ

#### データクラス定義
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class EpisodeMetadata:
    slug: str                    # 20250618-automation-pipeline
    title: str                   # エピソードタイトル
    description: str             # エピソード説明
    pub_date: datetime           # 公開日時
    duration_seconds: int        # 再生時間（秒）
    file_size_bytes: int         # ファイルサイズ
    mp3_url: str                # S3 URL
    guid: str                   # repo-abc123-20250618-automation-pipeline
    spotify_url: Optional[str] = None  # Spotify URL（検証後に設定）
    
    @classmethod
    def from_file_path(cls, file_path: str, base_url: str, commit_sha: str):
        """ファイルパスからメタデータを生成"""
        pass
    
    def to_rss_item(self) -> dict:
        """RSS item用辞書に変換"""
        pass
```

#### メタデータ抽出
```python
def extract_metadata(file_path: str, base_url: str, commit_sha: str) -> EpisodeMetadata:
    """MP3ファイルからメタデータを抽出"""
    
    # ファイル名からslug抽出
    filename = os.path.basename(file_path)
    slug = filename.replace('.mp3', '')
    
    # ID3タグ読み込み
    audio_file = mutagen.File(file_path)
    title = audio_file.get('TIT2', [slug])[0]
    description = audio_file.get('COMM::eng', [''])[0]
    
    # ファイル情報
    file_size = os.path.getsize(file_path)
    duration = int(audio_file.info.length)
    
    # URL生成
    year = slug[:4]
    mp3_url = f"{base_url}/podcast/{year}/{slug}.mp3"
    guid = f"repo-{commit_sha[:7]}-{slug}"
    
    # 公開日時（ファイル名から抽出）
    date_str = slug[:8]  # YYYYMMDD
    pub_date = datetime.strptime(date_str, '%Y%m%d')
    
    return EpisodeMetadata(
        slug=slug,
        title=title,
        description=description,
        pub_date=pub_date,
        duration_seconds=duration,
        file_size_bytes=file_size,
        mp3_url=mp3_url,
        guid=guid
    )
```

### 2. RSS生成インターフェース

#### RSS Builder
```python
from feedgen.feed import FeedGenerator
from typing import List

class RSSBuilder:
    def __init__(self, feed_config: dict):
        self.config = feed_config
        
    def build_feed(self, episodes: List[EpisodeMetadata]) -> str:
        """エピソードリストからRSSフィードを生成"""
        
        fg = FeedGenerator()
        
        # フィード基本設定
        fg.title(self.config['title'])
        fg.description(self.config['description'])
        fg.link(href=self.config['link'])
        fg.language(self.config['language'])
        fg.lastBuildDate(datetime.now(timezone.utc))
        fg.generator('Spotify Podcast Automation v1.0')
        
        # Podcast固有設定
        fg.podcast.itunes_category('Technology')
        fg.podcast.itunes_explicit('false')
        fg.podcast.itunes_author(self.config['author'])
        fg.podcast.itunes_summary(self.config['description'])
        
        # エピソード追加（新しい順）
        sorted_episodes = sorted(episodes, 
                               key=lambda x: x.pub_date, 
                               reverse=True)
        
        for episode in sorted_episodes:
            fe = fg.add_entry()
            fe.title(episode.title)
            fe.description(episode.description)
            fe.guid(episode.guid)
            fe.pubDate(episode.pub_date.replace(tzinfo=timezone.utc))
            
            # エンクロージャー（音声ファイル）
            fe.enclosure(
                url=episode.mp3_url,
                length=str(episode.file_size_bytes),
                type='audio/mpeg'
            )
            
            # iTunes固有設定
            fe.podcast.itunes_duration(
                self._seconds_to_duration(episode.duration_seconds)
            )
            fe.podcast.itunes_explicit('false')
        
        return fg.rss_str(pretty=True).decode('utf-8')
    
    def _seconds_to_duration(self, seconds: int) -> str:
        """秒をHH:MM:SS形式に変換"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
```

### 3. 検証結果インターフェース

#### 検証結果データクラス
```python
@dataclass
class VerificationResult:
    success: bool
    episode_guid: str
    attempts_made: int
    time_taken_seconds: int
    spotify_episode_id: Optional[str] = None
    spotify_url: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_summary(self) -> dict:
        """GitHub Actions Summary用の辞書に変換"""
        return {
            'status': '✅ 成功' if self.success else '❌ 失敗',
            'guid': self.episode_guid,
            'attempts': self.attempts_made,
            'duration': f"{self.time_taken_seconds}秒",
            'spotify_url': self.spotify_url or 'N/A',
            'error': self.error_message or 'なし'
        }
```

## データ交換仕様

### 1. GitHub Actions環境変数

#### 入力変数
```yaml
env:
  # AWS設定
  AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
  AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  AWS_S3_BUCKET: ${{ secrets.AWS_S3_BUCKET }}
  AWS_REGION: us-east-1
  
  # Spotify設定
  SPOTIFY_CLIENT_ID: ${{ secrets.SPOTIFY_CLIENT_ID }}
  SPOTIFY_CLIENT_SECRET: ${{ secrets.SPOTIFY_CLIENT_SECRET }}
  SPOTIFY_REFRESH_TOKEN: ${{ secrets.SPOTIFY_REFRESH_TOKEN }}
  SPOTIFY_SHOW_ID: ${{ secrets.SPOTIFY_SHOW_ID }}
  
  # 通知設定
  SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
  
  # システム設定
  BASE_URL: https://cdn.yourpodcast.com
  MAX_RETRY_ATTEMPTS: "3"
  SPOTIFY_POLL_INTERVAL: "30"
  SPOTIFY_MAX_ATTEMPTS: "10"
```

#### 出力変数
```yaml
outputs:
  episode-slug:
    description: "処理したエピソードのslug"
    value: ${{ steps.extract-metadata.outputs.slug }}
    
  mp3-url:
    description: "S3にアップロードされたMP3のURL"
    value: ${{ steps.upload.outputs.mp3-url }}
    
  rss-url:
    description: "更新されたRSSフィードのURL"
    value: ${{ steps.deploy-rss.outputs.rss-url }}
    
  spotify-url:
    description: "Spotifyエピソード URL（検証成功時）"
    value: ${{ steps.verify-spotify.outputs.spotify-url }}
    
  verification-status:
    description: "Spotify反映確認の結果（success/failed）"
    value: ${{ steps.verify-spotify.outputs.status }}
```

### 2. ログフォーマット

#### 構造化ログ
```json
{
    "timestamp": "2025-06-18T10:30:00.000Z",
    "level": "INFO",
    "event_type": "episode_processing_start",
    "episode_slug": "20250618-automation-pipeline",
    "commit_sha": "abc123def",
    "workflow_run_id": "123456789"
}

{
    "timestamp": "2025-06-18T10:30:15.000Z",
    "level": "INFO", 
    "event_type": "s3_upload_complete",
    "episode_slug": "20250618-automation-pipeline",
    "s3_key": "podcast/2025/20250618-automation-pipeline.mp3",
    "file_size_bytes": 25600000,
    "upload_duration_seconds": 12.5
}

{
    "timestamp": "2025-06-18T10:32:30.000Z",
    "level": "INFO",
    "event_type": "spotify_verification_complete",
    "episode_slug": "20250618-automation-pipeline", 
    "verification_attempts": 3,
    "verification_duration_seconds": 90,
    "spotify_episode_id": "4GI3dxEafwap1sFiTGPKd1",
    "success": true
}
```

## エラーレスポンス仕様

### 1. 外部API エラー

#### Spotify API エラー
```json
{
    "error": {
        "status": 401,
        "message": "Invalid access token"
    }
}
```

#### S3 エラー
```python
# boto3 例外
ClientError: {
    'Error': {
        'Code': 'NoSuchBucket',
        'Message': 'The specified bucket does not exist',
        'BucketName': 'non-existent-bucket'
    }
}
```

### 2. 内部エラー処理

#### エラーコード定義
```python
class ErrorCodes:
    # ファイル関連
    FILE_NOT_FOUND = "E001"
    INVALID_FILE_FORMAT = "E002" 
    FILE_SIZE_EXCEEDED = "E003"
    
    # API関連
    S3_UPLOAD_FAILED = "E101"
    SPOTIFY_AUTH_FAILED = "E102"
    SPOTIFY_TIMEOUT = "E103"
    
    # データ関連
    DUPLICATE_GUID = "E201"
    INVALID_METADATA = "E202"
    RSS_GENERATION_FAILED = "E203"
```

#### エラーレスポンス統一フォーマット
```python
@dataclass
class APIError:
    error_code: str
    message: str
    details: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }
```

## セキュリティ仕様

### 1. 認証情報管理
- **GitHub Secrets**: 機密情報の暗号化保存
- **環境変数**: ランタイムでの安全な受け渡し
- **トークン有効期限**: Spotify token の1時間制限に対応

### 2. 通信セキュリティ
- **HTTPS強制**: 全ての外部API通信
- **TLS 1.2以上**: 最小バージョン要件
- **証明書検証**: SSL証明書の自動検証

### 3. アクセス制御
- **IAM Role**: AWS最小権限アクセス
- **CORS設定**: S3バケットの適切なCORS設定
- **パブリックアクセス**: RSS/MP3のSpotify要件対応