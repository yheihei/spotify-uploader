# RSSのエピソード内のタイトル、description、imageなどをカスタマイズしたい

## 目的

現状SpotifyのRSSは下記のようなサンプルの通り出力されると思っている。

```
<?xml version="1.0" encoding="UTF-8"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0" xmlns:anchor="https://anchor.fm/xmlns" xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:psc="http://podlove.org/simple-chapters">
	<channel>
		<title><![CDATA[エンジニアの生存戦略ラジオ]]></title>
		<description><![CDATA[バックエンドエンジニアの「わいこ」がインプットした技術情報をひたすらアウトプットする番組]]></description>
		<link>https://qiita.com/yheihei</link>
		<generator>Anchor Podcasts</generator>
		<lastBuildDate>Wed, 18 Jun 2025 08:38:09 GMT</lastBuildDate>
		<atom:link href="https://anchor.fm/s/1063a53ac/podcast/rss" rel="self" type="application/rss+xml"/>
		<author><![CDATA[わいこ]]></author>
		<copyright><![CDATA[わいこ]]></copyright>
		<language><![CDATA[ja]]></language>
		<atom:link rel="hub" href="https://pubsubhubbub.appspot.com/"/>
		<itunes:author>わいこ</itunes:author>
		<itunes:summary>バックエンドエンジニアの「わいこ」がインプットした技術情報をひたすらアウトプットする番組</itunes:summary>
		<itunes:type>episodic</itunes:type>
		<itunes:owner>
			<itunes:name>わいこ</itunes:name>
			<itunes:email>yheihei0126@gmail.com</itunes:email>
		</itunes:owner>
		<itunes:explicit>false</itunes:explicit>
		<itunes:category text="Technology"/>
		<itunes:image href="https://d3t3ozftmdmh3i.cloudfront.net/staging/podcast_uploaded_nologo/43894531/43894531-1750152528703-6d7aa138fe182.jpg"/>
		<item>
			<title><![CDATA[なぜClaudeCodeなのか?]]></title>
			<description><![CDATA[<p>CursorでもなくWindsurfでもなく、なぜ今のタイミングでClaude Codeを使っているのか。語ってみました</p>
]]></description>
			<link>https://podcasters.spotify.com/pod/show/yheihei/episodes/ClaudeCode-e34c1lr</link>
			<guid isPermaLink="false">892ad84c-a15e-4245-a8be-3eaded28dcb0</guid>
			<dc:creator><![CDATA[わいこ]]></dc:creator>
			<pubDate>Tue, 17 Jun 2025 09:29:22 GMT</pubDate>
			<enclosure url="https://anchor.fm/s/1063a53ac/podcast/play/104252539/https%3A%2F%2Fd3ctxlq1ktw2nl.cloudfront.net%2Fstaging%2F2025-5-17%2F402314792-44100-2-1b69bdfa4a748.m4a" length="3887101" type="audio/x-m4a"/>
			<itunes:summary>&lt;p&gt;CursorでもなくWindsurfでもなく、なぜ今のタイミングでClaude Codeを使っているのか。語ってみました&lt;/p&gt;
</itunes:summary>
			<itunes:explicit>false</itunes:explicit>
			<itunes:duration>00:04:00</itunes:duration>
			<itunes:image href="https://d3t3ozftmdmh3i.cloudfront.net/staging/podcast_uploaded_nologo/43894531/43894531-1750152528703-6d7aa138fe182.jpg"/>
			<itunes:season>1</itunes:season>
			<itunes:episode>1</itunes:episode>
			<itunes:episodeType>full</itunes:episodeType>
		</item>
	</channel>
</rss>
```
item のなかのtitleやdescription、image、season、episode、episodeTypeなどをカスタムできる必要はないか？ でないと適当な情報でエピソードが公開されてしますのではないか？
