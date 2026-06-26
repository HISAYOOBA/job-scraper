"""
ハローワーク求人・求職情報提供サービス API を使い、東京23区のアルバイト求人データを
取得してGoogleスプレッドシートに蓄積するスクリプト。

GitHub Actions から毎週月曜9時に実行される想定。

処理フロー:
  1. トークン発行
  2. 求人一覧データ取得（データID一覧の確認・東京都データの存在確認）
  3. 指定求人データ取得（データID: M113＝民間職業紹介事業者用・一般求人・東京都、ページ送り）
  4. 就業場所住所コードで東京23区のみ抽出
  5. スプレッドシート上の既存 求人番号(kjno) と比較し、新規レコードのみ追加
  6. トークン破棄

データID M113 は「民間職業紹介事業者用」の東京都求人。
利用団体の登録区分（民間職業紹介事業者）に対応するデータIDを使用すること。
"""

import os
import sys
import datetime

import gspread
from google.auth import default

from hellowork_client import HelloWorkClient, HelloWorkAPIError
from ward_codes import is_tokyo_23_ward, ward_name

# ── 設定 ──
DATA_ID = "M113"  # 民間職業紹介事業者用・一般求人・東京都
SHEET_NAME = "ハローワーク求人"

# 就業場所住所コードは shgbsjusho1_c 〜 shgbsjusho4_c のいずれかに入る可能性があるため、
# 優先順位を付けて先頭からチェックする
ADDRESS_CODE_FIELDS = ["shgbsjusho1_c", "shgbsjusho2_c", "shgbsjusho3_c", "shgbsjusho4_c"]

# スプレッドシートの列順（求人番号を先頭に置き、重複チェックのキーとして使う）
SHEET_HEADERS = [
    "取得日",
    "求人番号(kjno)",
    "受付年月日",
    "区名",
    "事業所名",
    "事業所住所",
    "就業場所住所",
    "職種",
    "仕事内容",
    "雇用形態",
    "賃金",
    "基本給",
    "選考担当者TEL",
    "選考担当者FAX",
    "選考担当者メール",
]

TODAY = datetime.date.today().strftime("%Y/%m/%d")


def get_address_code(record: dict) -> str:
    for field in ADDRESS_CODE_FIELDS:
        code = record.get(field, "")
        if code:
            return code
    return ""


def record_to_row(record: dict, ward: str) -> list:
    """ハローワークAPIのレコード(dict)をスプレッドシートの行データに変換する"""
    return [
        TODAY,
        record.get("kjno", ""),
        record.get("uktkymd_seireki", ""),
        ward,
        record.get("jgshmei", ""),
        record.get("jgshjusho", ""),
        record.get("shgbsjusho", ""),
        record.get("sksu", ""),
        record.get("shigoto_ny", ""),
        record.get("koyokeitai_n", ""),
        record.get("chgn", ""),
        record.get("khky", ""),
        record.get("snktts_tel", ""),
        record.get("snktts_fax", ""),
        record.get("snktts_mail", ""),
    ]


def get_or_create_sheet(sh, name: str, headers: list):
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=10000, cols=len(headers) + 2)
        ws.append_row(headers)
    return ws


def fetch_existing_kjno_set(ws) -> set:
    """
    スプレッドシートに既に登録済みの求人番号(kjno)集合を取得する。
    SHEET_HEADERS の "求人番号(kjno)" の列位置（B列＝2列目）を取得する。
    """
    col_index = SHEET_HEADERS.index("求人番号(kjno)") + 1  # gspreadは1始まり
    values = ws.col_values(col_index)
    # 先頭行はヘッダーなので除外
    return set(v for v in values[1:] if v)


def main():
    user_id = os.environ.get("HELLOWORK_USER_ID")
    password = os.environ.get("HELLOWORK_PASSWORD")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")

    if not user_id or not password:
        print("エラー: HELLOWORK_USER_ID / HELLOWORK_PASSWORD が設定されていません。", file=sys.stderr)
        sys.exit(1)
    if not spreadsheet_id:
        print("エラー: SPREADSHEET_ID が設定されていません。", file=sys.stderr)
        sys.exit(1)

    # ── Googleスプレッドシート認証（GitHub Actions WIF経由） ──
    creds, _ = default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    ws = get_or_create_sheet(sh, SHEET_NAME, SHEET_HEADERS)

    existing_kjno = fetch_existing_kjno_set(ws)
    print(f"既存の求人番号: {len(existing_kjno)}件")

    # ── ハローワークAPI呼び出し ──
    client = HelloWorkClient(user_id, password)

    try:
        client.get_token()
        print("トークン発行に成功しました。")

        # データID一覧を確認し、対象データIDが存在するか検証する
        data_ids = client.list_data_ids()
        target = next((d for d in data_ids if d["data_id"] == DATA_ID), None)
        if target is None:
            print(f"エラー: データID {DATA_ID} が一覧に見つかりませんでした。"
                  f" 利用団体の登録区分（民間職業紹介事業者）を確認してください。", file=sys.stderr)
            sys.exit(1)
        print(f"対象データ: {target['data_name']}（全{target['count']}件、{target['page']}ページ）")

        BATCH_SIZE = 200  # この件数ごとにスプレッドシートへ書き込み、途中失敗時のデータ消失を防ぐ
        pending_rows = []
        total_fetched = 0
        total_23ward = 0
        total_added = 0

        def flush_pending():
            nonlocal pending_rows, total_added
            if pending_rows:
                ws.append_rows(pending_rows, value_input_option="USER_ENTERED")
                total_added += len(pending_rows)
                print(f"  → {len(pending_rows)}件をスプレッドシートに書き込みました（累計{total_added}件）")
                pending_rows = []

        for record in client.iter_all_kyujin(DATA_ID, total_pages=target["page"]):
            total_fetched += 1
            kjno = record.get("kjno", "")

            address_code = get_address_code(record)
            ward = ward_name(address_code)
            if not is_tokyo_23_ward(address_code):
                continue
            total_23ward += 1

            if kjno in existing_kjno:
                continue  # 既にスプレッドシートに登録済み

            pending_rows.append(record_to_row(record, ward))
            existing_kjno.add(kjno)  # 同一実行内での重複も防ぐ

            if len(pending_rows) >= BATCH_SIZE:
                flush_pending()

        flush_pending()  # 残りを書き込み

        print(f"取得件数: {total_fetched}件 / 23区該当: {total_23ward}件 / 新規追加: {total_added}件")

        if total_added == 0:
            print("新規追加データはありませんでした。")

    except HelloWorkAPIError as e:
        print(f"ハローワークAPIエラー: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.del_token()
        print("トークンを破棄しました。")


if __name__ == "__main__":
    main()
