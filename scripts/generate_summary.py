#!/usr/bin/env python3
"""
GitHub Actions Summary Generation Script

This script generates a comprehensive summary for GitHub Actions workflow runs,
displaying episode information, processing results, and relevant links.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class SummaryGenerator:
    """GitHub Actions summary generator"""
    
    def __init__(self):
        self.summary_file = os.environ.get('GITHUB_STEP_SUMMARY')
        if not self.summary_file:
            logger.warning("GITHUB_STEP_SUMMARY environment variable not set")

    def generate_summary(self, episode_slug: str, episode_title: str,
                        audio_url: str, rss_url: str,
                        spotify_url: Optional[str] = None,
                        verification_status: str = 'unknown',
                        upload_duration: Optional[str] = None,
                        rss_duration: Optional[str] = None,
                        verification_duration: Optional[str] = None,
                        attempts_made: Optional[str] = None) -> str:
        """Generate markdown summary"""
        
        # Determine status emoji and color
        if verification_status == 'success':
            status_emoji = '✅'
            status_text = '成功'
            status_color = 'green'
        elif verification_status == 'failed':
            status_emoji = '❌'
            status_text = '失敗'
            status_color = 'red'
        else:
            status_emoji = '⚠️'
            status_text = '不明'
            status_color = 'yellow'
        
        # Generate timestamp
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Build summary markdown
        summary = f"""# {status_emoji} Podcast Episode Deployment Summary

## Episode Information
| 項目 | 値 |
|------|-----|
| **エピソード名** | {episode_title} |
| **スラッグ** | `{episode_slug}` |
| **処理状況** | {status_emoji} {status_text} |
| **処理完了時刻** | {timestamp} |

## Deployment Results

### 📁 Audio File Upload
| 項目 | 値 |
|------|-----|
| **Audio URL** | [🔗 ファイルを開く]({audio_url}) |
| **アップロード時間** | {upload_duration or 'N/A'} |

### 📡 RSS Feed
| 項目 | 値 |
|------|-----|
| **RSS URL** | [🔗 フィードを開く]({rss_url}) |
| **生成時間** | {rss_duration or 'N/A'} |

### 🎵 Spotify Integration
| 項目 | 値 |
|------|-----|
| **検証状況** | {status_emoji} {status_text} |
| **検証時間** | {verification_duration or 'N/A'} |
| **試行回数** | {attempts_made or 'N/A'} |
"""

        if spotify_url:
            summary += f"| **Spotify URL** | [🎧 Spotifyで聴く]({spotify_url}) |\n"
        else:
            summary += "| **Spotify URL** | まだ利用できません |\n"

        # Add next steps section
        summary += "\n## Next Steps\n\n"
        
        if verification_status == 'success':
            summary += """✅ **エピソードが正常に配信されました！**

- Spotifyでエピソードが利用可能になりました
- RSSフィードが更新されました
- 他のポッドキャストプラットフォームでも数時間以内に利用可能になります

### 📢 推奨アクション
1. [Spotify URL]({}) で音質と内容を確認
2. ソーシャルメディアでエピソードを宣伝
3. 分析データを確認して配信状況をモニター
""".format(spotify_url if spotify_url else '#')
        
        elif verification_status == 'failed':
            summary += """❌ **Spotify での検証に失敗しました**

### 🔍 トラブルシューティング
1. **RSS フィード確認**: [RSS URL]({}) が正しく生成されているか確認
2. **Spotify for Podcasters**: 手動でインデックス更新をリクエスト
3. **再実行**: 一時的な問題の場合、ワークフローを再実行してみてください
4. **サポート**: 問題が続く場合は開発チームに連絡してください

### 📋 確認事項
- [ ] RSSフィードにエピソードが含まれているか
- [ ] 音声ファイルが正しくアップロードされているか
- [ ] Spotify for Podcastersの設定に問題がないか
""".format(rss_url)
        
        else:
            summary += """⚠️ **検証状況が不明です**

ワークフローは完了しましたが、Spotify での検証結果が不明です。
手動で確認することをお勧めします。
"""

        # Add technical details section
        summary += f"\n## Technical Details\n\n"
        summary += "```json\n"
        summary += json.dumps({
            'episode_slug': episode_slug,
            'episode_title': episode_title,
            'audio_url': audio_url,
            'rss_url': rss_url,
            'spotify_url': spotify_url,
            'verification_status': verification_status,
            'upload_duration': upload_duration,
            'rss_duration': rss_duration,
            'verification_duration': verification_duration,
            'attempts_made': attempts_made,
            'timestamp': timestamp
        }, indent=2)
        summary += "\n```\n"
        
        # Add workflow links
        workflow_url = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
        repository = os.environ.get('GITHUB_REPOSITORY', '')
        run_id = os.environ.get('GITHUB_RUN_ID', '')
        
        if repository and run_id:
            summary += f"\n## Workflow Information\n\n"
            summary += f"- **Repository**: [{repository}]({workflow_url}/{repository})\n"
            summary += f"- **Run ID**: [{run_id}]({workflow_url}/{repository}/actions/runs/{run_id})\n"
            summary += f"- **Triggered by**: {os.environ.get('GITHUB_ACTOR', 'Unknown')}\n"
            summary += f"- **Event**: {os.environ.get('GITHUB_EVENT_NAME', 'Unknown')}\n"
        
        return summary

    def write_summary(self, summary_content: str):
        """Write summary to GitHub Actions summary file"""
        if self.summary_file:
            try:
                with open(self.summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary_content)
                logger.info(f"Summary written to {self.summary_file}")
            except Exception as e:
                logger.error(f"Failed to write summary file: {e}")
        else:
            # Fallback: print to stdout
            print("\n" + "="*80)
            print("GITHUB ACTIONS SUMMARY")
            print("="*80)
            print(summary_content)
            print("="*80)

    def add_job_summary(self, title: str, status: str, details: dict):
        """Add a job summary section"""
        if not self.summary_file:
            return
        
        try:
            # Determine emoji based on status
            emoji_map = {
                'success': '✅',
                'failure': '❌',
                'warning': '⚠️',
                'info': 'ℹ️'
            }
            emoji = emoji_map.get(status, 'ℹ️')
            
            summary_addition = f"\n### {emoji} {title}\n\n"
            
            # Add details as table
            if details:
                summary_addition += "| 項目 | 値 |\n|------|-----|\n"
                for key, value in details.items():
                    summary_addition += f"| **{key}** | {value} |\n"
            
            summary_addition += "\n"
            
            # Append to existing summary
            with open(self.summary_file, 'a', encoding='utf-8') as f:
                f.write(summary_addition)
                
        except Exception as e:
            logger.error(f"Failed to add job summary: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate GitHub Actions summary for podcast deployment'
    )
    parser.add_argument('--episode-slug', required=True, help='Episode slug')
    parser.add_argument('--episode-title', required=True, help='Episode title')
    parser.add_argument('--audio-url', required=True, help='Audio file URL (MP3 or WAV)')
    parser.add_argument('--rss-url', required=True, help='RSS feed URL')
    parser.add_argument('--spotify-url', help='Spotify episode URL')
    parser.add_argument('--verification-status', default='unknown', help='Verification status')
    parser.add_argument('--upload-duration', help='Upload duration')
    parser.add_argument('--rss-duration', help='RSS generation duration')
    parser.add_argument('--verification-duration', help='Verification duration')
    parser.add_argument('--attempts-made', help='Number of verification attempts')
    
    args = parser.parse_args()
    
    try:
        # Generate summary
        generator = SummaryGenerator()
        
        summary_content = generator.generate_summary(
            episode_slug=args.episode_slug,
            episode_title=args.episode_title,
            audio_url=args.audio_url,
            rss_url=args.rss_url,
            spotify_url=args.spotify_url,
            verification_status=args.verification_status,
            upload_duration=args.upload_duration,
            rss_duration=args.rss_duration,
            verification_duration=args.verification_duration,
            attempts_made=args.attempts_made
        )
        
        # Write summary
        generator.write_summary(summary_content)
        
        logger.info("✅ Summary generated successfully")
        
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        print(f"::error title=Summary Generation Error::{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()