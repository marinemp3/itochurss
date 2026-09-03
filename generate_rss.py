import os
import sys
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone, timedelta
import re
import urllib3

# SSL警告を無効化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定
TARGET_URL = "https://www.itochu-research.com/ja/report/"
OUTPUT_FILENAME = "feed.xml"
TZ = timezone(timedelta(hours=9))

def fetch_and_parse(url):
    """指定されたURLのHTMLを取得し、レポート情報を抽出する"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        print(f"ページの取得に成功しました (ステータスコード: {response.status_code})")
        
    except requests.exceptions.RequestException as e:
        print(f"ページの取得に失敗しました: {e}")
        sys.exit(1)

    soup = BeautifulSoup(response.text, 'html.parser')
    
    print("HTML解析を開始します...")
    
    # list_setクラスを持つ全ての要素を取得
    list_sets = soup.find_all('div', class_='list_set')
    print(f"見つかったレポートアイテム数: {len(list_sets)}")
    
    if not list_sets:
        print("レポートアイテムが見つかりませんでした。")
        return []

    report_items = []
    
    for idx, item in enumerate(list_sets, 1):
        try:
            # --- 1. 日付の抽出 ---
            date_elem = item.find('p', class_='date')
            if not date_elem:
                print(f"アイテム {idx}: 日付が見つかりません - スキップ")
                continue
                
            date_text = date_elem.get_text(strip=True)
            
            # 日付形式: "YYYY.MM.DD" を解析
            try:
                report_date = datetime.strptime(date_text, "%Y.%m.%d").replace(tzinfo=TZ)
            except ValueError:
                print(f"アイテム {idx}: 日付形式が不正 - {date_text}")
                continue

            # --- 2. タイトルの抽出 ---
            # 方法: ttl_box内のp.ttlを探す
            ttl_box = item.find('div', class_='ttl_box')
            if not ttl_box:
                print(f"アイテム {idx}: ttl_boxが見つかりません - スキップ")
                continue
                
            title_elem = ttl_box.find('p', class_='ttl')
            if not title_elem:
                print(f"アイテム {idx}: p.ttlが見つかりません - スキップ")
                continue
                
            title = title_elem.get_text(strip=True)
            if not title:
                print(f"アイテム {idx}: タイトルが空です - スキップ")
                continue

            # --- 3. リンクの抽出 ---
            # ttl_boxの親要素からaタグを探す（3つ目のaタグがレポートへのリンク）
            link = None
            parent = ttl_box.parent
            if parent:
                # 親要素がaタグの場合
                if parent.name == 'a':
                    link = parent.get('href')
                else:
                    # 親要素の中からaタグを探す
                    link_elem = parent.find('a')
                    if link_elem:
                        link = link_elem.get('href')
            
            # もし見つからなければ、item全体からaタグを探す（ttl_boxを含むaタグ）
            if not link:
                # ttl_boxを含むaタグを探す
                for a_tag in item.find_all('a'):
                    if a_tag.find('div', class_='ttl_box'):
                        link = a_tag.get('href')
                        break
            
            if not link:
                print(f"アイテム {idx}: リンクが見つかりません - スキップ")
                continue
                
            # リンクが相対パスの場合、絶対URLに変換
            if link.startswith('/'):
                link = "https://www.itochu-research.com" + link
            elif not link.startswith('http'):
                link = "https://www.itochu-research.com/ja/report/" + link

            # --- 4. カテゴリ（タグ）の抽出 ---
            categories = []
            
            # tag_iconからカテゴリを取得
            tag_icon = item.find('ul', class_='tag_icon')
            if tag_icon:
                tag_items = tag_icon.find_all('li')
                for tag_li in tag_items:
                    tag_text = tag_li.get_text(strip=True)
                    if tag_text:
                        categories.append(tag_text)

            # デバッグ情報
            print(f"✓ アイテム {idx}: {title[:50]}... ({date_text})")
            if categories:
                print(f"  カテゴリ: {', '.join(categories)}")

            report_item = {
                'title': title,
                'link': link,
                'pubDate': report_date,
                'categories': categories,
                'description': f"伊藤忠総研のレポート: {title}",
            }
            report_items.append(report_item)
            
        except Exception as e:
            print(f"アイテム {idx} の解析中にエラーが発生しました: {e}")
            continue

    return report_items

def generate_rss(items, output_path):
    """抽出したアイテムからRSSフィードを生成する"""
    if not items:
        print("RSSに含めるアイテムがありません。")
        return False

    fg = FeedGenerator()
    fg.title("伊藤忠総研 レポート RSS")
    fg.description("株式会社伊藤忠総研が公開するレポートの最新情報を配信します。")
    fg.link(href="https://www.itochu-research.com/ja/report/", rel="alternate")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(TZ))

    # 各アイテムをフィードに追加
    for item in items:
        try:
            fe = fg.add_entry()
            fe.title(item['title'])
            fe.link(href=item['link'])
            fe.pubDate(item['pubDate'])
            fe.description(item['description'])
            if item.get('categories'):
                for cat in item['categories']:
                    fe.category(term=cat)
        except Exception as e:
            print(f"RSSエントリの追加中にエラーが発生しました: {e}")
            continue

    # RSSファイルを出力
    try:
        rss_str = fg.rss_str(pretty=True)
        with open(output_path, 'wb') as f:
            f.write(rss_str)
        print(f"\nRSSフィードが正常に生成されました: {output_path}")
        print(f"含まれているアイテム数: {len(items)}")
        return True
    except Exception as e:
        print(f"RSSファイルの書き込み中にエラーが発生しました: {e}")
        return False

def main():
    print("=" * 50)
    print("伊藤忠総研 RSSフィード生成ツール")
    print("=" * 50)
    
    print("\n1. レポートページから情報を取得中...")
    reports = fetch_and_parse(TARGET_URL)
    
    if reports:
        # 取得したレポートを日付の新しい順にソート
        reports.sort(key=lambda x: x['pubDate'], reverse=True)
        print(f"\n2. {len(reports)}件のレポートを取得しました。")
        
        print("\n3. RSSフィードを生成中...")
        success = generate_rss(reports, OUTPUT_FILENAME)
        
        if success:
            print("\n[ステッカー] RSSフィードの生成が完了しました！")
            print(f"ファイル: {OUTPUT_FILENAME}")
            
            # 最初の3件をプレビュー表示
            print("\n=== 生成されたRSSのプレビュー（最初の3件） ===")
            for i, item in enumerate(reports[:3], 1):
                print(f"\n{i}. タイトル: {item['title']}")
                print(f"   日付: {item['pubDate'].strftime('%Y-%m-%d')}")
                print(f"   リンク: {item['link']}")
                if item.get('categories'):
                    print(f"   カテゴリ: {', '.join(item['categories'])}")
        else:
            print("\n[ステッカー] RSSフィードの生成に失敗しました。")
            sys.exit(1)
    else:
        print("\n[ステッカー] レポートが見つかりませんでした。")
        sys.exit(1)

if __name__ == "__main__":
    main()
