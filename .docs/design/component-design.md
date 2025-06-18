# コンポーネント設計書

## 概要

本システムの各コンポーネントの詳細設計と実装仕様を定義します。

## コンポーネント構成

### 1. GitHub Actions Workflow (`release.yml`)

#### 責務
- MP3ファイル検出とトリガー処理
- 各処理ステップのオーケストレーション
- エラーハンドリングと通知

#### 設計仕様
```yaml
# トリガー条件
on:
  push:
    paths: ['episodes/**/*.mp3']
    branches: [main]
  workflow_dispatch:

# 実行環境
runs-on: ubuntu-latest

# タイムアウト設定
timeout-minutes: 2
```

#### ジョブ構成
1. **setup**: 環境設定とメタデータ抽出
2. **upload**: S3アップロード（並列実行）
3. **rss-generation**: RSS生成とデプロイ
4. **spotify-verification**: Spotify反映確認
5. **notification**: 結果通知

#### エラーハンドリング戦略
- 各ステップでの`continue-on-error: false`
- リトライロジックの実装
- 失敗時の詳細ログ出力

### 2. RSS生成コンポーネント (`build_rss.py`)

#### 責務
- 既存エピソードの情報収集
- feedgenを使用したRSS XML生成
- S3への安全なデプロイ

#### クラス設計
```python
class RSSGenerator:
    def __init__(self, s3_client, bucket_name, base_url):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.base_url = base_url
        
    def collect_episodes(self) -> List[Episode]:
        """S3から既存エピソード情報を収集"""
        pass
        
    def generate_rss(self, episodes: List[Episode]) -> str:
        """feedgenでRSS XML生成"""
        pass
        
    def deploy_rss(self, rss_content: str) -> bool:
        """アトミックなRSSデプロイ"""
        pass

class Episode:
    def __init__(self, slug: str, title: str, description: str, 
                 pub_date: datetime, mp3_url: str, guid: str):
        self.slug = slug
        self.title = title
        self.description = description
        self.pub_date = pub_date
        self.mp3_url = mp3_url
        self.guid = guid
```

#### メタデータ抽出ロジック
- **ファイル名パース**: `YYYYMMDD-title-kebab.mp3`
- **ID3タグ読み込み**: `mutagen`ライブラリ使用
- **GUID生成**: `repo-{sha[:7]}-{slug}`形式

#### RSS生成仕様
```python
def generate_rss(self, episodes):
    fg = FeedGenerator()
    
    # フィード基本情報
    fg.title('Your Podcast Title')
    fg.description('Podcast Description')
    fg.link(href=self.base_url)
    fg.language('ja')
    fg.lastBuildDate(datetime.now(timezone.utc))
    
    # エピソード追加
    for episode in episodes:
        fe = fg.add_entry()
        fe.title(episode.title)
        fe.description(episode.description)
        fe.guid(episode.guid)
        fe.enclosure(episode.mp3_url, 0, 'audio/mpeg')
        fe.pubDate(episode.pub_date)
    
    return fg.rss_str(pretty=True)
```

#### アトミックデプロイ実装
```python
def deploy_rss(self, rss_content: str) -> bool:
    temp_key = 'rss.xml.new'
    final_key = 'rss.xml'
    
    try:
        # 一時ファイルアップロード
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=temp_key,
            Body=rss_content,
            ContentType='application/rss+xml',
            CacheControl='public, max-age=300'
        )
        
        # アトミック移動
        self.s3_client.copy_object(
            CopySource={'Bucket': self.bucket_name, 'Key': temp_key},
            Bucket=self.bucket_name,
            Key=final_key
        )
        
        # 一時ファイル削除
        self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=temp_key
        )
        
        return True
    except Exception as e:
        logger.error(f"RSS deploy failed: {e}")
        return False
```

### 3. Spotify検証コンポーネント (`check_spotify.py`)

#### 責務
- Spotify Web APIを使用したエピソード確認
- ポーリングベースの反映待機
- 検証結果のレポート

#### クラス設計  
```python
class SpotifyVerifier:
    def __init__(self, client_id: str, client_secret: str, 
                 refresh_token: str, show_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.show_id = show_id
        self.access_token = None
        
    def authenticate(self) -> bool:
        """OAuth refresh tokenで認証"""
        pass
        
    def check_episode_exists(self, guid: str) -> bool:
        """指定GUIDのエピソード存在確認"""
        pass
        
    def verify_with_polling(self, guid: str, 
                          max_attempts: int = 10,
                          interval_seconds: int = 30) -> dict:
        """ポーリングベースの検証"""
        pass
```

#### 認証実装
```python
def authenticate(self) -> bool:
    auth_url = 'https://accounts.spotify.com/api/token'
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': self.refresh_token,
        'client_id': self.client_id,
        'client_secret': self.client_secret
    }
    
    response = requests.post(auth_url, data=data)
    
    if response.status_code == 200:
        self.access_token = response.json()['access_token']
        return True
    
    return False
```

#### ポーリング実装
```python
def verify_with_polling(self, guid: str, max_attempts=10, interval=30):
    for attempt in range(max_attempts):
        if self.check_episode_exists(guid):
            return {
                'success': True,
                'attempts': attempt + 1,
                'time_taken': (attempt + 1) * interval
            }
        
        if attempt < max_attempts - 1:
            time.sleep(interval)
    
    return {
        'success': False,
        'attempts': max_attempts,
        'time_taken': max_attempts * interval
    }
```

### 4. ユーティリティコンポーネント

#### S3アップローダー (`s3_uploader.py`)
```python
class S3Uploader:
    def __init__(self, s3_client, bucket_name):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
    
    def upload_with_retry(self, local_path: str, s3_key: str, 
                         max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                self.s3_client.upload_file(
                    local_path, self.bucket_name, s3_key,
                    ExtraArgs={
                        'ContentType': 'audio/mpeg',
                        'CacheControl': 'public, max-age=300'
                    }
                )
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2 ** attempt)  # 指数バックオフ
        
        return False
```

#### 通知コンポーネント (`notifier.py`)
```python
class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send_success(self, episode_slug: str, spotify_url: str):
        payload = {
            'text': f'✅ エピソード `{episode_slug}` が正常に配信されました',
            'attachments': [{
                'color': 'good',
                'fields': [
                    {'title': 'Spotify URL', 'value': spotify_url, 'short': False}
                ]
            }]
        }
        requests.post(self.webhook_url, json=payload)
    
    def send_failure(self, episode_slug: str, error_message: str):
        payload = {
            'text': f'❌ エピソード `{episode_slug}` の配信に失敗しました',
            'attachments': [{
                'color': 'danger',
                'fields': [
                    {'title': 'エラー', 'value': error_message, 'short': False}
                ]
            }]
        }
        requests.post(self.webhook_url, json=payload)
```

## エラーハンドリング戦略

### 1. 分類別エラー処理

#### 一時的エラー（リトライ対象）
- S3接続エラー
- Spotify API レート制限
- ネットワークタイムアウト

#### 永続的エラー（即座に失敗）
- 認証情報不正
- ファイル形式エラー  
- GUID重複

### 2. ログ設計
```python 
import logging
import json

class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_event(self, event_type: str, **kwargs):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            **kwargs
        }
        self.logger.info(json.dumps(log_entry))
```

## 設定管理

### 環境変数
```bash
# AWS設定
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY= 
AWS_S3_BUCKET=
AWS_REGION=

# Spotify設定
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REFRESH_TOKEN=
SPOTIFY_SHOW_ID=

# 通知設定  
SLACK_WEBHOOK_URL=

# その他
BASE_URL=https://your-cdn.com
MAX_RETRY_ATTEMPTS=3
SPOTIFY_POLL_INTERVAL=30
SPOTIFY_MAX_ATTEMPTS=10
```

## テスト戦略

### 1. 単体テスト
- 各コンポーネントクラスのメソッドテスト
- モック使用によるAPI依存排除
- エッジケースのテストカバレッジ

### 2. 統合テスト  
- 実際のS3/Spotify APIを使用したE2Eテスト
- GitHub Actionsワークフローの動作確認
- 障害シナリオテスト

### 3. パフォーマンステスト
- 2分以内の実行時間検証
- 並列処理のベンチマーク
- メモリ使用量監視