import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
import gspread
from google.auth import default

# ── 認証（GitHub Actions WIF経由で自動取得） ──
creds, _ = default(scopes=[
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])
gc = gspread.authorize(creds)
sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TODAY = datetime.date.today().strftime("%Y/%m/%d")


# ════════════════════════════════════════
# 1. マイナビバイト
# ════════════════════════════════════════
def scrape_mynavi(max_pages=3):
    results = []
    base_url = "https://baito.mynavi.jp/list/?ar=030&employmentStatus=2"
    # ar=030: 東京23区, employmentStatus=2: アルバイト

    for page in range(1, max_pages + 1):
        url = f"{base_url}&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            cards = soup.select("div.cassetteRecruit")
            if not cards:
                break

            for card in cards:
                title_el   = card.select_one("h3.cassetteRecruit__name a")
                company_el = card.select_one("p.cassetteRecruit__company")
                area_el    = card.select_one("dd.cassetteRecruit__detail--place")
                salary_el  = card.select_one("dd.cassetteRecruit__detail--wage")
                employ_el  = card.select_one("span.cassetteRecruit__employmentStatus")
                date_el    = card.select_one("span.cassetteRecruit__update")

                title   = title_el.get_text(strip=True) if title_el else ""
                url_job = "https://baito.mynavi.jp" + title_el["href"] if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                area    = area_el.get_text(strip=True) if area_el else ""
                salary  = salary_el.get_text(strip=True) if salary_el else ""
                employ  = employ_el.get_text(strip=True) if employ_el else "アルバイト"
                pub     = date_el.get_text(strip=True) if date_el else TODAY

                results.append([TODAY, "マイナビバイト", title, company, area, salary, employ, url_job, pub])

            time.sleep(2)

        except Exception as e:
            print(f"[マイナビバイト] page={page} エラー: {e}")
            break

    print(f"[マイナビバイト] {len(results)}件取得")
    return results


# ════════════════════════════════════════
# 2. 求人ボックス
# ════════════════════════════════════════
def scrape_kyujinbox(max_pages=3):
    results = []
    base_url = "https://kyujinbox.com/jobs?keyword=アルバイト&location=東京都23区"

    for page in range(1, max_pages + 1):
        url = f"{base_url}&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            cards = soup.select("article.job-item")
            if not cards:
                break

            for card in cards:
                title_el   = card.select_one("h2.job-item__title a")
                company_el = card.select_one("span.job-item__company")
                area_el    = card.select_one("span.job-item__location")
                salary_el  = card.select_one("span.job-item__salary")
                employ_el  = card.select_one("span.job-item__employment-type")
                date_el    = card.select_one("time")

                title   = title_el.get_text(strip=True) if title_el else ""
                url_job = title_el["href"] if title_el else ""
                if url_job and not url_job.startswith("http"):
                    url_job = "https://kyujinbox.com" + url_job
                company = company_el.get_text(strip=True) if company_el else ""
                area    = area_el.get_text(strip=True) if area_el else ""
                salary  = salary_el.get_text(strip=True) if salary_el else ""
                employ  = employ_el.get_text(strip=True) if employ_el else "アルバイト"
                pub     = date_el["datetime"][:10].replace("-", "/") if date_el and date_el.get("datetime") else TODAY

                results.append([TODAY, "求人ボックス", title, company, area, salary, employ, url_job, pub])

            time.sleep(2)

        except Exception as e:
            print(f"[求人ボックス] page={page} エラー: {e}")
            break

    print(f"[求人ボックス] {len(results)}件取得")
    return results


# ════════════════════════════════════════
# 3. エンゲージ
# ════════════════════════════════════════
def scrape_engage(max_pages=3):
    results = []
    base_url = "https://en-gage.net/user/search/?employmentStatus=4&prefCode=13&areaCode=1300"
    # employmentStatus=4: アルバイト, prefCode=13: 東京都

    for page in range(1, max_pages + 1):
        url = f"{base_url}&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            cards = soup.select("li.job-list__item")
            if not cards:
                break

            for card in cards:
                title_el   = card.select_one("h2.job-list__item-title a")
                company_el = card.select_one("p.job-list__item-company")
                area_el    = card.select_one("span.job-list__item-location")
                salary_el  = card.select_one("span.job-list__item-salary")
                employ_el  = card.select_one("span.job-list__item-employment")
                date_el    = card.select_one("time.job-list__item-date")

                title   = title_el.get_text(strip=True) if title_el else ""
                url_job = "https://en-gage.net" + title_el["href"] if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                area    = area_el.get_text(strip=True) if area_el else ""
                salary  = salary_el.get_text(strip=True) if salary_el else ""
                employ  = employ_el.get_text(strip=True) if employ_el else "アルバイト"
                pub     = date_el.get_text(strip=True) if date_el else TODAY

                results.append([TODAY, "エンゲージ", title, company, area, salary, employ, url_job, pub])

            time.sleep(2)

        except Exception as e:
            print(f"[エンゲージ] page={page} エラー: {e}")
            break

    print(f"[エンゲージ] {len(results)}件取得")
    return results


# ════════════════════════════════════════
# メイン処理
# ════════════════════════════════════════
def get_or_create_sheet(name):
    """シート名で既存シートを取得、なければ新規作成"""
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=5000, cols=10)
        ws.append_row(["取得日", "媒体", "求人タイトル", "会社名", "勤務地", "給与", "雇用形態", "掲載URL", "掲載日"])
        return ws

def main():
    all_results = []
    all_results += scrape_mynavi(max_pages=3)
    all_results += scrape_kyujinbox(max_pages=3)
    all_results += scrape_engage(max_pages=3)

    if not all_results:
        print("取得件数0件。終了します。")
        return

    # 媒体ごとに別シートに書き込み
    from itertools import groupby
    all_results.sort(key=lambda x: x[1])  # 媒体名でソート
    for media, rows in groupby(all_results, key=lambda x: x[1]):
        ws = get_or_create_sheet(media)
        ws.append_rows(list(rows))
        print(f"[{media}] スプレッドシートに書き込み完了")

    # 全件まとめシートにも追記
    ws_all = get_or_create_sheet("全媒体")
    ws_all.append_rows(all_results)

    print(f"\n✅ 合計 {len(all_results)}件 書き込み完了")

if __name__ == "__main__":
    main()
