# Google Colab用 Convex Finance 統合スクレイピングコード
# CVX、cvxCRV、Curveプールのすべての情報を抽出・出力するバージョン

import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from google.colab import files

def setup_chrome_driver():
    """Google Colab用のChromeドライバーをセットアップ"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("Chromeドライバーの初期化が完了しました")
    except Exception as e:
        print(f"Chromeドライバーの初期化エラー: {e}")
        return None

    return driver

def wait_for_data_loading(driver):
    """データの読み込みを待機"""
    wait = WebDriverWait(driver, 30)

    try:
        # ページが完全に読み込まれるまで待機
        print("ページの読み込みを待機中...")
        time.sleep(10)
        
        # cvxCRVとCVXの両方のセクションを待機
        wait.until(EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'cvxCRV') or contains(text(), 'CVX')]")))
        print("cvxCRVとCVXセクションが読み込まれました")
        time.sleep(15)  # データの完全な読み込みを待機

    except Exception as e:
        print(f"待機中にエラーが発生しました: {e}")
        print("強制的に待機を継続します...")
        time.sleep(15)

def click_show_all_buttons(driver):
    """「Show All」ボタンをクリックしてプール一覧を表示"""
    try:
        wait = WebDriverWait(driver, 10)
        
        # 「Show All Curve Pools」ボタンをクリック
        all_pools_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Show All Curve Pools')]")))
        all_pools_button.click()
        print("Show All Curve Poolsボタンをクリックしました")
        time.sleep(3)
        
        # 「Show All Curve Lending Vaults」ボタンをクリック
        all_vaults_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Show All Curve Lending Vaults')]")))
        all_vaults_button.click()
        print("Show All Curve Lending Vaultsボタンをクリックしました")
        time.sleep(3)
        
    except Exception as e:
        print(f"Show Allボタンのクリックに失敗: {e}")

def extract_cvx_data_formatted(html_content):
    """HTMLからCVXの情報を抽出（フォーマット版）- vAPRとTVLのみ"""
    soup = BeautifulSoup(html_content, 'html.parser')

    # デバッグ: すべてのh2タグを確認
    print("=== CVXセクション検索デバッグ ===")
    h2_tags = soup.find_all('h2')
    for i, h2 in enumerate(h2_tags):
        print(f"H2[{i}]: {h2.get_text().strip()}")
    
    # CVXセクションを探す（より柔軟な検索）
    cvx_section = None
    for h2 in soup.find_all('h2'):
        h2_text = h2.get_text().strip()
        if 'CVX' in h2_text:
            cvx_section = h2.find_parent()
            print(f"CVXセクションを発見: {h2_text}")
            break

    if not cvx_section:
        print("CVXセクションが見つかりませんでした")
        # デバッグ: HTMLの一部を出力
        print("HTMLの最初の1000文字:")
        print(html_content[:1000])
        return None

    # CVXの情報を抽出（vAPRとTVLのみ）
    vapr = None
    tvl = None

    # より広範囲のdivを検索
    all_divs = cvx_section.find_all('div')
    print(f"CVXセクション内のdiv数: {len(all_divs)}")
    
    for i, div in enumerate(all_divs):
        div_text = div.get_text().strip()
        if div_text and ('vAPR' in div_text or 'TVL' in div_text):
            print(f"CVX関連div[{i}]: {div_text}")
        
        # vAPR
        if 'vAPR' in div_text and '%' in div_text:
            percentage_matches = re.findall(r'(\d+\.?\d*)%', div_text)
            if percentage_matches:
                vapr = percentage_matches[0]
                print(f"CVX vAPR: {vapr}%")
        
        # TVL
        elif 'TVL' in div_text and '$' in div_text:
            dollar_matches = re.findall(r'\$([\d\.]+[kmb]?)', div_text, re.IGNORECASE)
            if dollar_matches:
                tvl = dollar_matches[0]
                print(f"CVX TVL: ${tvl}")

    return {
        'vapr': vapr,
        'tvl': tvl
    }

def extract_cvxcrv_data_formatted(html_content):
    """HTMLからcvxCRVのMax vAPRとTVLを抽出（フォーマット版）"""
    soup = BeautifulSoup(html_content, 'html.parser')

    # デバッグ: cvxCRVセクション検索
    print("=== cvxCRVセクション検索デバッグ ===")
    
    # cvxCRVセクションを探す（より柔軟な検索）
    cvxcrv_section = None
    for h2 in soup.find_all('h2'):
        h2_text = h2.get_text().strip()
        if 'cvxCRV' in h2_text:
            cvxcrv_section = h2.find_parent()
            print(f"cvxCRVセクションを発見: {h2_text}")
            break

    if not cvxcrv_section:
        print("cvxCRVセクションが見つかりませんでした")
        return None

    # Max vAPRを抽出
    max_vapr_gov = None
    max_vapr_stable = None

    # Max vAPRを含むdivを検索
    for div in cvxcrv_section.find_all('div', class_='jsx-d6fb22cbc31fb3e5'):
        div_text = div.get_text().strip()
        if 'Max vAPR' in div_text and '%' in div_text:
            print(f"Max vAPR divを発見: '{div_text}'")

            # パーセンテージの値を抽出
            percentages = re.findall(r'(\d+\.?\d*)%', div_text)
            print(f"発見されたパーセンテージ: {percentages}")

            if len(percentages) >= 2:
                # 有効なパーセンテージを抽出（100%や0%を除外）
                valid_percentages = []
                for pct in percentages:
                    pct_float = float(pct)
                    if pct_float > 0 and pct_float < 100:
                        valid_percentages.append(pct)

                if len(valid_percentages) >= 2:
                    max_vapr_gov = valid_percentages[0]
                    max_vapr_stable = valid_percentages[1]
                    print(f"Max vAPR - 100% gov token rewards: {max_vapr_gov}%")
                    print(f"Max vAPR - 100% stablecoin rewards: {max_vapr_stable}%")
            break

    # TVLを抽出
    tvl = None

    # TVLを含むdivを検索
    for div in cvxcrv_section.find_all('div', class_='jsx-d6fb22cbc31fb3e5'):
        div_text = div.get_text().strip()
        if 'TVL' in div_text and '$' in div_text:
            print(f"TVL divを発見: '{div_text}'")

            # ドル記号付きの値を抽出
            dollar_matches = re.findall(r'\$([\d\.]+[kmb]?)', div_text, re.IGNORECASE)
            if dollar_matches:
                tvl = dollar_matches[0]
                print(f"TVL: ${tvl}")
            break

    return {
        'max_vapr_gov': max_vapr_gov,
        'max_vapr_stable': max_vapr_stable,
        'tvl': tvl
    }

def extract_curve_pools_data(html_content):
    """HTMLからCurveプールのデータを抽出"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # プールデータ抽出
    anchors = soup.select('a[href*="/stake/"]')
    results = []

    for a in anchors:
        pool_name = a.get_text(strip=True)
        
        # "Or"で始まるプール名はスキップ
        if pool_name.startswith("Or"):
            continue

        parent = a
        verticals = []
        for _ in range(10):
            parent = parent.find_parent("div")
            if not parent:
                break
            verticals = parent.find_all("div", class_=lambda x: x and "vertical" in x)
            if len(verticals) >= 1:
                break

        def safe_get(i):
            return verticals[i].get_text(" ", strip=True) if len(verticals) > i else ""

        # vAPRの情報を取得（2番目のvertical div）
        vapr_text = safe_get(1)
        
        # デバッグ: vAPRテキストを出力
        if vapr_text:
            print(f"プール '{pool_name}' のvAPRテキスト: '{vapr_text}'")
        
        # Current vAPRとProjected vAPRを抽出
        current_vapr = ""
        projected_vapr = ""
        
        # パーセンテージのパターンを検索（より厳密に）
        vapr_matches = re.findall(r'(\d+\.?\d*)\s*%', vapr_text)
        if vapr_matches:
            # 最初のパーセンテージをCurrent vAPRとして使用
            current_vapr = vapr_matches[0] + "%"
            print(f"Current vAPR発見: {current_vapr}")
        
        # projectedのパターンを検索
        proj_match = re.search(r'proj\.\s*(\d+\.?\d*)\s*%', vapr_text, re.IGNORECASE)
        if proj_match:
            projected_vapr = proj_match.group(1) + "%"
            print(f"Projected vAPR発見: {projected_vapr}")
        
        # Current vAPRまたはProjected vAPRが空欄の場合のみ、500%を設定
        if not current_vapr and vapr_text:  # vapr_textが存在する場合のみ
            current_vapr = "500%"
            print(f"Current vAPRが空欄のため500%を設定: {pool_name}")
        if not projected_vapr and vapr_text:  # vapr_textが存在する場合のみ
            projected_vapr = "500%"
            print(f"Projected vAPRが空欄のため500%を設定: {pool_name}")
        
        # veCRV boostを抽出
        vecrv_boost = ""
        boost_match = re.search(r'veCRV boost:\s*([^,\s]+)', vapr_text)
        if boost_match:
            vecrv_boost = boost_match.group(1)
        
        # Remarks（"Or"で始まる文字列）を抽出
        remarks = ""
        or_match = re.search(r'Or\s+[^<]+', vapr_text)
        if or_match:
            remarks = or_match.group(0).strip()
        
        # TVLを取得（4番目のvertical div）
        tvl = safe_get(3)

        results.append([pool_name, current_vapr, projected_vapr, vecrv_boost, remarks, tvl])

    return results

def scrape_convex_data_integrated():
    """Convex FinanceからCVX、cvxCRV、Curveプールのデータをスクレイピング（統合版）"""
    url = "https://curve.convexfinance.com/stake"

    driver = setup_chrome_driver()
    if not driver:
        return None

    try:
        print("ページにアクセス中...")
        driver.get(url)

        # データの読み込みを待機
        wait_for_data_loading(driver)

        # Show Allボタンをクリックしてプール一覧を表示
        click_show_all_buttons(driver)

        html_content = driver.page_source
        print("HTMLを取得しました")
        
        # デバッグ用: HTMLをファイルに保存
        with open('debug_html.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("デバッグ用HTMLファイルを保存しました: debug_html.html")

        # CVX、cvxCRV、Curveプールのデータを抽出
        cvx_data = extract_cvx_data_formatted(html_content)
        cvxcrv_data = extract_cvxcrv_data_formatted(html_content)
        curve_pools_data = extract_curve_pools_data(html_content)

        if cvx_data:
            print("\n=== CVX データ ===")
            print(f"vAPR: {cvx_data['vapr']}%")
            print(f"TVL: ${cvx_data['tvl']}")

        if cvxcrv_data:
            print("\n=== cvxCRV データ ===")
            print(f"Max vAPR - 100% gov token rewards: {cvxcrv_data['max_vapr_gov']}%")
            print(f"Max vAPR - 100% stablecoin rewards: {cvxcrv_data['max_vapr_stable']}%")
            print(f"TVL: ${cvxcrv_data['tvl']}")

        if curve_pools_data:
            print(f"\n=== Curveプール データ ===")
            print(f"取得したプール数: {len(curve_pools_data)}")

        return {
            'cvx': cvx_data,
            'cvxcrv': cvxcrv_data,
            'curve_pools': curve_pools_data
        }

    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return None

    finally:
        driver.quit()

def save_and_download_csv(df, filename):
    """CSVファイルを保存して自動ダウンロード"""
    try:
        # CSVファイルを保存
        df.to_csv(filename, index=False)
        print(f"ファイルを保存しました: {filename}")

        # Google Colabで自動ダウンロード
        files.download(filename)
        print("✅ ファイルが自動ダウンロードされました")

    except Exception as e:
        print(f"ファイルの保存・ダウンロード中にエラーが発生しました: {e}")
        # フォールバック: 通常の保存のみ
        df.to_csv(filename, index=False)
        print(f"ファイルを保存しました: {filename}")

def main():
    """メイン実行関数"""
    print("Convex Finance 統合データスクレイピングを開始します...")

    # 現在時刻を取得
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"実行時刻: {current_time}")

    data = scrape_convex_data_integrated()

    if data:
        # CVXデータのDataFrameを作成
        if data['cvx']:
            cvx_df_data = {
                'timestamp': [current_time],
                'token': ['CVX'],
                'vapr': [f"{data['cvx']['vapr']}%" if data['cvx']['vapr'] else 'N/A'],
                'tvl': [f"${data['cvx']['tvl']}" if data['cvx']['tvl'] else 'N/A']
            }
            cvx_df = pd.DataFrame(cvx_df_data)
            
            # CVXファイル名を生成
            cvx_filename = f'cvx_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            # CVXファイルを保存して自動ダウンロード
            save_and_download_csv(cvx_df, cvx_filename)
            
            print("\n=== CVX 抽出結果 ===")
            print(cvx_df)
        
        # cvxCRVデータのDataFrameを作成
        if data['cvxcrv']:
            cvxcrv_df_data = {
                'timestamp': [current_time],
                'pool': ['CRV'],
                'stake': ['cvxCRV'],
                'max_vapr_gov_token_rewards': [f"{data['cvxcrv']['max_vapr_gov']}%" if data['cvxcrv']['max_vapr_gov'] else 'N/A'],
                'max_vapr_stablecoin_rewards': [f"{data['cvxcrv']['max_vapr_stable']}%" if data['cvxcrv']['max_vapr_stable'] else 'N/A'],
                'tvl': [f"${data['cvxcrv']['tvl']}" if data['cvxcrv']['tvl'] else 'N/A']
            }
            cvxcrv_df = pd.DataFrame(cvxcrv_df_data)
            
            # cvxCRVファイル名を生成
            cvxcrv_filename = f'cvxcrv_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            # cvxCRVファイルを保存して自動ダウンロード
            save_and_download_csv(cvxcrv_df, cvxcrv_filename)
            
            print("\n=== cvxCRV 抽出結果 ===")
            print(cvxcrv_df)

        # CurveプールデータのDataFrameを作成
        if data['curve_pools']:
            curve_pools_df = pd.DataFrame(data['curve_pools'], columns=["Pool", "Current vAPR", "Projected vAPR", "veCRV boost", "Remarks", "TVL"])
            
            # タイムスタンプ列を追加
            curve_pools_df.insert(0, 'timestamp', current_time)
            
            # Curveプールファイル名を生成
            curve_pools_filename = f'curve_pools_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            # Curveプールファイルを保存して自動ダウンロード
            save_and_download_csv(curve_pools_df, curve_pools_filename)
            
            print("\n=== Curveプール 抽出結果 ===")
            print(f"取得したプール数: {len(curve_pools_df)}")
            print(curve_pools_df.head(10))  # 最初の10行を表示

        # データの確認
        print("\n=== データ確認 ===")
        if data['cvx']:
            print("CVXデータ:")
            print(f"  vAPR: {data['cvx']['vapr']}%")
            print(f"  TVL: ${data['cvx']['tvl']}")
        
        if data['cvxcrv']:
            print("cvxCRVデータ:")
            print(f"  Max vAPR - 100% gov token rewards: {data['cvxcrv']['max_vapr_gov']}%")
            print(f"  Max vAPR - 100% stablecoin rewards: {data['cvxcrv']['max_vapr_stable']}%")
            print(f"  TVL: ${data['cvxcrv']['tvl']}")
        
        if data['curve_pools']:
            print(f"Curveプールデータ:")
            print(f"  取得したプール数: {len(data['curve_pools'])}")
        
        print("データの抽出が完了しました")
    else:
        print("データの取得に失敗しました")

if __name__ == "__main__":
    main()
