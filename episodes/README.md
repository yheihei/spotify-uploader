# Episodes Directory

このディレクトリにMP3ファイルを配置すると、GitHub Actions がトリガーされて自動的にSpotifyへの配信処理が開始されます。

## ファイル命名規則

MP3ファイルは以下の命名規則に従って命名してください：

```
YYYYMMDD-episode-title-in-kebab-case.mp3
```

### 例:
- `20250618-first-episode.mp3`
- `20250619-automation-workflow.mp3`
- `20250620-tech-discussion.mp3`

## ファイル要件

- **形式**: MP3 (.mp3)
- **最大サイズ**: 500MB 推奨
- **音質**: 128kbps以上推奨
- **ID3タグ**: タイトル、説明などのメタデータを含めることを推奨

## 配信プロセス

1. MP3ファイルをこのディレクトリに追加
2. `main`ブランチにコミット・プッシュ
3. GitHub Actions が自動実行される
4. 処理完了後、GitHub Actions Summaryで結果を確認

## トラブルシューティング

### よくある問題

**ワークフローがトリガーされない**
- ファイル名が正しい形式か確認
- `main`ブランチにプッシュされているか確認
- ファイルが`.mp3`拡張子を持っているか確認

**アップロードが失敗する**
- ファイルサイズが大きすぎないか確認
- AWS認証情報が正しく設定されているか確認

**Spotify検証が失敗する**
- RSS フィードが正しく生成されているか確認
- Spotify for Podcasters の設定を確認
- 15分程度待ってから再確認

## 手動実行

特定のエピソードを手動で処理したい場合：

1. GitHub Actions の "Podcast Release Automation" ワークフローに移動
2. "Run workflow" をクリック
3. MP3ファイルのパスを指定して実行

## ファイル例

テスト用のサンプルファイルを作成するには：

```bash
# サンプルファイル作成（実際の音声ファイルに置き換えてください）
touch episodes/20250618-sample-episode.mp3
```

**注意**: 実際のMP3音声ファイルに置き換える必要があります。