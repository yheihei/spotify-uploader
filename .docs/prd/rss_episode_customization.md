# PRD: RSSエピソード内容のカスタマイズ機能

## 概要

現在のSpotify Podcast Automation Systemでは、RSSフィード内のエピソード情報が限定的で、多くの要素が自動生成または固定値となっている。より適切な情報でポッドキャストエピソードを公開するため、エピソード毎のカスタマイズ機能を実装する。

## 背景と課題

### 現在の問題点

1. **エピソードタイトルの自動生成**: slugから生成されるタイトルが適切でない場合がある
2. **説明文の貧弱性**: デフォルトの説明文が「Episode: {slug}」のみで情報不足
3. **エピソード画像の未設定**: ポッドキャスト全体の画像のみで、エピソード固有の画像が設定できない
4. **シーズン・エピソード番号の未設定**: iTunes標準のシーズン・エピソード番号が設定されていない
5. **エピソードタイプの未設定**: full/trailer/bonusなどのエピソードタイプが設定されていない

### 現在の実装状況

`scripts/build_rss.py`の`EpisodeMetadata`クラスで管理されている要素：
- ✅ title（メタデータから取得可能）
- ✅ description（メタデータから取得可能）
- ✅ duration（メタデータから取得可能）
- ✅ guid（メタデータから取得可能）
- ❌ episode_image（未実装）
- ❌ season（未実装）
- ❌ episode_number（未実装）
- ❌ episode_type（未実装）

## 要求仕様

### 機能要件

#### 1. エピソードメタデータの拡張

以下の要素をS3オブジェクトメタデータで設定可能にする：

```python
@dataclass
class EpisodeMetadata:
    # 既存フィールド
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
    
    # 新規追加フィールド
    episode_image_url: Optional[str] = None
    season: Optional[int] = None
    episode_number: Optional[int] = None
    episode_type: Optional[str] = 'full'  # full/trailer/bonus
    itunes_summary: Optional[str] = None
    itunes_subtitle: Optional[str] = None
    itunes_keywords: Optional[str] = None
    itunes_explicit: Optional[str] = 'no'  # yes/no/clean
```

#### 2. エピソードディレクトリ構造の変更

従来の`episodes/`直下の音声ファイル配置から以下の構造に変更：

```
episodes/
├── 20250618-first-episode/
│   ├── audio.mp3             # 音声ファイル（任意の名前）
│   ├── episode_data.json     # エピソードメタデータ
│   └── thumbnail.jpg         # エピソード画像（オプション）
├── 20250619-special-bonus/
│   ├── audio.wav
│   ├── episode_data.json
│   └── cover.png
└── README.md
```

#### 3. episode_data.json スキーマ

各エピソードディレクトリに配置する`episode_data.json`の構造：

```json
{
  "title": "エピソードタイトル",
  "description": "エピソードの詳細説明",
  "itunes_summary": "iTunes用の詳細説明（HTMLタグ使用可能）",
  "itunes_subtitle": "iTunes用サブタイトル",
  "itunes_keywords": ["keyword1", "keyword2", "keyword3"],
  "itunes_explicit": "no",
  "season": 1,
  "episode_number": 1,
  "episode_type": "full",
  "episode_image": "thumbnail.jpg",
  "pub_date": "2025-06-18T09:00:00Z",
  "guid": "custom-episode-guid",
  "duration_seconds": 240,
  "custom_metadata": {
    "any_custom_field": "value"
  }
}
```

**必須フィールド**：
- `title`: エピソードタイトル
- `description`: エピソード説明

**オプションフィールド**：
- `itunes_summary`: iTunes用詳細説明（未設定時はdescriptionを使用）
- `itunes_subtitle`: iTunes用サブタイトル
- `itunes_keywords`: iTunes用キーワード配列
- `itunes_explicit`: yes/no/clean（デフォルト: no）
- `season`: シーズン番号（デフォルト: 1）
- `episode_number`: エピソード番号（未設定時は自動採番）
- `episode_type`: full/trailer/bonus（デフォルト: full）
- `episode_image`: 同じディレクトリ内の画像ファイル名
- `pub_date`: 公開日時（未設定時はディレクトリ名から推定）
- `guid`: エピソードGUID（未設定時は自動生成）
- `duration_seconds`: 音声長（未設定時は音声ファイルから取得）
- `custom_metadata`: 将来拡張用のカスタムフィールド

#### 4. RSS生成機能の拡張

`generate_rss`メソッドで以下の要素を出力：

```xml
<item>
    <title><![CDATA[カスタムタイトル]]></title>
    <description><![CDATA[カスタム説明文]]></description>
    <itunes:summary>iTunes用詳細説明</itunes:summary>
    <itunes:subtitle>iTunes用サブタイトル</itunes:subtitle>
    <itunes:image href="エピソード固有画像URL"/>
    <itunes:season>1</itunes:season>
    <itunes:episode>1</itunes:episode>
    <itunes:episodeType>full</itunes:episodeType>
    <itunes:keywords>keyword1,keyword2,keyword3</itunes:keywords>
    <itunes:explicit>no</itunes:explicit>
    <!-- 既存要素 -->
    <guid isPermaLink="false">episode-guid</guid>
    <pubDate>Tue, 17 Jun 2025 09:29:22 GMT</pubDate>
    <enclosure url="audio-url" length="size" type="audio/mpeg"/>
    <itunes:duration>00:04:00</itunes:duration>
</item>
```

#### 5. デフォルト値の設定

メタデータが設定されていない場合のデフォルト値：
- `episode_image_url`: ポッドキャスト全体の画像を使用
- `season`: 1
- `episode_number`: 発行日順に自動採番
- `episode_type`: 'full'
- `itunes_summary`: description と同じ値
- `itunes_subtitle`: 未設定
- `itunes_keywords`: 未設定
- `itunes_explicit`: 'no'

### 非機能要件

#### 1. パフォーマンス要件
- GitHub Actions実行時間≤2分の制約を維持
- S3メタデータ取得の追加時間≤10秒

#### 2. 互換性要件
- 既存のエピソードとの後方互換性を維持
- 新しいメタデータが設定されていない既存エピソードも正常に動作

#### 3. 拡張性要件
- 将来的な追加メタデータに対応可能な設計
- メタデータ検証機能との連携

## 実装方針

### Phase 1: ディレクトリ構造対応
1. エピソードディレクトリスキャン機能の実装
2. `episode_data.json`読み込み機能の実装
3. 音声ファイル自動検出機能の実装
4. エピソード画像ファイル処理機能の実装

### Phase 2: データモデル拡張
1. `EpisodeMetadata`クラスに新フィールド追加
2. `from_episode_directory`メソッドの実装
3. JSONスキーマ検証機能の実装
4. デフォルト値処理ロジックの実装

### Phase 3: S3アップロード機能拡張
1. エピソード画像のS3アップロード機能
2. 音声ファイル一括アップロード機能
3. ディレクトリ構造に対応したS3パス生成
4. 既存エピソードとの後方互換性確保

### Phase 4: RSS生成機能拡張
1. `generate_rss`メソッドのiTunesタグ追加
2. エピソード番号自動採番ロジック実装
3. エピソード画像URL生成機能
4. JSON形式メタデータからRSS要素への変換

### Phase 5: テスト・検証
1. 単体テストの追加（JSONスキーマ検証含む）
2. RSS検証ツールでの確認
3. Spotify取り込み検証
4. ディレクトリ構造移行テスト

## 成功指標

1. **機能完全性**: 全ての新メタデータ要素がRSSに正しく反映される
2. **パフォーマンス**: GitHub Actions実行時間が2分以内を維持
3. **互換性**: 既存エピソードが正常に動作する
4. **検証**: Spotifyで新しいメタデータが正しく表示される

## リスク

1. **ディレクトリ構造変更の影響**: 既存のワークフローとの互換性問題
2. **JSONスキーマ検証エラー**: 不正なJSONでエピソード処理が失敗する可能性
3. **RSS検証エラー**: iTunes標準に準拠しない値でRSSが無効になる可能性
4. **Spotify取り込み影響**: 新しいメタデータがSpotify取り込みに影響する可能性
5. **ファイルサイズ増加**: 大量のメタデータによるリポジトリサイズの増加

## 補足事項

- エピソード画像はS3に保存し、public-readで配信
- `episode_data.json`はGitリポジトリで管理し、バージョン履歴を保持
- JSONファイルによりメタデータの編集・管理が容易
- RSS生成エラー時は既存動作にフォールバック
- 既存のS3ベースエピソードとの併存が可能な設計とする

## ディレクトリ構造移行計画

### 移行ステップ
1. **併存期間**: 旧形式（`episodes/audio.mp3`）と新形式（`episodes/dir/`）を同時サポート
2. **段階的移行**: 新しいエピソードから新形式を使用
3. **旧エピソード移行**: 必要に応じて旧エピソードを新形式に移行

### 後方互換性
- 既存の`podcast/YYYY/slug.mp3`形式のS3オブジェクトも継続サポート
- S3メタデータからの情報取得も並行して維持

## 参考資料

- [iTunes RSS Tags](https://help.apple.com/itc/podcasts_connect/#/itcb54353390)
- [Spotify RSS Requirements](https://podcasters.spotify.com/terms/rss-specification)
- [JSON Schema Specification](https://json-schema.org/)
- [AWS S3 Object Metadata](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html)