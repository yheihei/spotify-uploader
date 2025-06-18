# 実装計画: RSSエピソード内容のカスタマイズ機能

## 概要
エピソードごとのメタデータを`episode_data.json`で管理し、RSSフィードに詳細なiTunes要素を出力する機能の実装計画。

## Phase 1: 基盤準備とデータモデル拡張 (1日目)

### 1.1 EpisodeMetadataクラスの拡張
- [ ] `scripts/build_rss.py`の`EpisodeMetadata`クラスに新フィールド追加
  - episode_image_url
  - season
  - episode_number
  - episode_type
  - itunes_summary
  - itunes_subtitle
  - itunes_keywords
  - itunes_explicit
- [ ] `from_dict`メソッドの更新（新フィールド対応）
- [ ] `to_dict`メソッドの更新（新フィールド対応）

### 1.2 ディレクトリ構造対応
- [ ] `from_episode_directory`クラスメソッドの実装
  - ディレクトリ内の音声ファイル自動検出（mp3/wav）
  - episode_data.json読み込み
  - エピソード画像ファイル検出
- [ ] ディレクトリ名からslugとpub_date推定ロジック

### 1.3 JSONスキーマ定義
- [ ] episode_data.jsonのJSONスキーマ作成
- [ ] スキーマ検証機能の実装
- [ ] デフォルト値処理ロジック

## Phase 2: エピソード処理機能の実装 (2日目)

### 2.1 エピソードディレクトリスキャン機能
- [ ] `collect_episode_directories`メソッドの実装
  - episodes/配下のディレクトリ検出
  - 旧形式（直接音声ファイル）との判別
- [ ] 後方互換性処理（既存のS3エピソード対応）

### 2.2 S3アップロード機能拡張
- [ ] `upload_s3.py`の拡張
  - エピソード画像アップロード機能
  - ディレクトリベースのアップロード処理
  - S3パス生成ロジック（podcast/{year}/{slug}/）

### 2.3 episode_data.json処理
- [ ] JSON読み込みとバリデーション
- [ ] 必須フィールドチェック
- [ ] デフォルト値の設定

## Phase 3: RSS生成機能の拡張 (3日目)

### 3.1 iTunes要素の追加
- [ ] `generate_rss`メソッドの更新
  - itunes:summary
  - itunes:subtitle
  - itunes:image (エピソード固有)
  - itunes:season
  - itunes:episode
  - itunes:episodeType
  - itunes:keywords
  - itunes:explicit (エピソード固有)

### 3.2 エピソード番号自動採番
- [ ] pub_date順でのエピソード番号自動採番ロジック
- [ ] シーズン番号のデフォルト値処理

### 3.3 エピソード画像URL生成
- [ ] S3上のエピソード画像パス生成
- [ ] フォールバック処理（ポッドキャスト全体画像）

## Phase 4: GitHub Actions対応 (4日目)

### 4.1 ワークフロー更新
- [ ] `.github/workflows/release.yml`の更新
  - ディレクトリ構造に対応した処理フロー
  - エピソード画像アップロード対応

### 4.2 メタデータ抽出スクリプト更新
- [ ] `extract_metadata.py`の拡張
  - episode_data.json対応
  - 音声ファイル自動検出

### 4.3 検証スクリプト更新
- [ ] `validate_metadata.py`の拡張
  - JSONスキーマ検証
  - 必須フィールドチェック

## Phase 5: テストとドキュメント (5日目)

### 5.1 単体テスト
- [ ] `test_build_rss.py`の拡張
  - 新フィールドのテスト
  - ディレクトリ構造対応テスト
  - JSONスキーマ検証テスト
- [ ] 後方互換性テスト

### 5.2 統合テスト
- [ ] エンドツーエンドテスト
  - ディレクトリ→S3→RSS生成の一連フロー
  - 旧形式との併存テスト

### 5.3 ドキュメント更新
- [ ] README.mdの更新
  - 新しいディレクトリ構造の説明
  - episode_data.jsonの記述方法
- [ ] サンプルエピソードの作成

## リスク管理

### 重要な考慮事項
1. **後方互換性**: 既存のS3エピソードが動作し続けること
2. **パフォーマンス**: GitHub Actions 2分制限の維持
3. **エラーハンドリング**: JSONエラー時のフォールバック
4. **検証**: RSS/iTunes規格への準拠

### テスト戦略
- 段階的リリース: まず新形式のサポートを追加し、旧形式も維持
- カナリアテスト: 1つのエピソードで新形式を試す
- ロールバック計画: 問題発生時は旧実装に戻す

## 実装順序の根拠

1. **データモデル先行**: 全ての機能の基盤となるため最初に実装
2. **処理機能**: データを扱う基本機能を次に実装
3. **RSS生成**: コア機能の実装
4. **CI/CD対応**: 自動化への組み込み
5. **テスト・文書**: 品質保証と利用者向け情報

## 成果物

1. 拡張された`EpisodeMetadata`クラス
2. ディレクトリベースのエピソード処理機能
3. iTunes準拠の詳細なRSSフィード
4. 更新されたGitHub Actionsワークフロー
5. 包括的なテストスイート
6. 利用者向けドキュメント

## 検証項目

- [ ] 全てのiTunes要素が正しくRSSに出力される
- [ ] エピソード画像が正しく表示される
- [ ] 既存エピソードが引き続き動作する
- [ ] GitHub Actions実行時間が2分以内
- [ ] Spotifyでメタデータが正しく表示される