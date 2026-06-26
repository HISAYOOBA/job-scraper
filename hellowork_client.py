"""
ハローワーク求人・求職情報提供サービス API クライアント

仕様書（別冊：求人情報提供サービス API インタフェース仕様書 第1.4版）に基づく実装。

API概要:
  - 認証: ユーザID + パスワードでトークンを取得（固定APIキーは存在しない）
  - トークンは取得当日のみ有効
  - リクエストはPOSTメソッドのみ
  - 1回の取得は最大1,000件まで（ページ送りで取得）
  - 検索条件（職種・地域・賃金等）での絞り込みは不可
  - レスポンスはXML形式（UTF-8, 改行コードLF）
  - メンテナンス時間: 毎日0時〜6時、月末21:30〜翌6時（アクセス不可）
"""

import time
import xml.etree.ElementTree as ET
from typing import Iterator

import requests

BASE_URL = "https://teikyo.hellowork.mhlw.go.jp/teikyo/api/2.0"

# データ取得・トークン操作の間に挟むスリープ（サーバー負荷軽減のため）
REQUEST_INTERVAL_SEC = 1.0


class HelloWorkAPIError(Exception):
    """ハローワークAPIの呼び出しで発生したエラー"""
    pass


class HelloWorkClient:
    def __init__(self, user_id: str, password: str, base_url: str = BASE_URL):
        self.user_id = user_id
        self.password = password
        self.base_url = base_url
        self.token: str | None = None

    # ────────────────────────────────
    # トークン発行処理 (2.3)
    # ────────────────────────────────
    def get_token(self) -> str:
        url = f"{self.base_url}/auth/getToken"
        params = {"id": self.user_id, "pass": self.password}
        res = requests.post(url, params=params, timeout=30)

        if res.status_code != 200:
            raise HelloWorkAPIError(
                f"トークン発行に失敗しました（HTTP {res.status_code}）。"
                f" ユーザIDまたはパスワードが間違っている可能性があります。"
            )

        root = ET.fromstring(res.content)
        token_el = root.find("token")
        if token_el is None or not token_el.text:
            raise HelloWorkAPIError("トークン発行のレスポンスに token が含まれていません。")

        self.token = token_el.text
        return self.token

    # ────────────────────────────────
    # トークン破棄処理 (2.4)
    # ────────────────────────────────
    def del_token(self) -> None:
        if not self.token:
            return
        url = f"{self.base_url}/auth/delToken"
        params = {"token": self.token}
        try:
            res = requests.post(url, params=params, timeout=30)
            if res.status_code != 200:
                print(f"[警告] トークン破棄に失敗しました（HTTP {res.status_code}）。"
                      f" 当日中は自動的に無効化されないため必要に応じて再確認してください。")
        finally:
            self.token = None

    # ────────────────────────────────
    # 求人一覧データ取得処理 (2.5)
    # ────────────────────────────────
    def list_data_ids(self) -> list[dict]:
        """
        取得可能なデータIDの一覧を取得する。
        各要素: {"data_id", "data_name", "count", "page"}
        """
        if not self.token:
            raise HelloWorkAPIError("トークンが未発行です。先に get_token() を呼んでください。")

        url = f"{self.base_url}/kyujin"
        params = {"token": self.token}
        res = requests.post(url, params=params, timeout=30)

        if res.status_code != 200:
            raise HelloWorkAPIError(f"求人一覧データ取得に失敗しました（HTTP {res.status_code}）。")

        root = ET.fromstring(res.content)
        items = []
        for data_el in root.findall(".//kyujin_list/data"):
            items.append({
                "data_id": _text(data_el, "data_id"),
                "data_name": _text(data_el, "data_name"),
                "count": int(_text(data_el, "count") or 0),
                "page": int(_text(data_el, "page") or 1),
            })
        return items

    # ────────────────────────────────
    # 指定求人データ取得処理 (2.6)
    # ────────────────────────────────
    def get_kyujin_page(self, data_id: str, page: int = 1) -> tuple[list[dict], int]:
        """
        指定データID・ページの求人情報データを取得する。

        戻り値: (求人レコードのリスト, 総ページ数)
        """
        if not self.token:
            raise HelloWorkAPIError("トークンが未発行です。先に get_token() を呼んでください。")

        url = f"{self.base_url}/kyujin/{data_id}/{page}"
        params = {"token": self.token}
        res = requests.post(url, params=params, timeout=60)

        if res.status_code != 200:
            raise HelloWorkAPIError(
                f"指定求人データ取得に失敗しました（data_id={data_id}, page={page}, HTTP {res.status_code}）。"
            )

        root = ET.fromstring(res.content)
        total_pages = int(_text(root, "page") or 1)

        records = []
        for data_el in root.findall(".//kyujin/data"):
            record = {child.tag: (child.text or "") for child in data_el}
            records.append(record)

        return records, total_pages

    def iter_all_kyujin(self, data_id: str) -> Iterator[dict]:
        """
        指定データIDの全ページを順に取得し、求人レコードを1件ずつ返すジェネレータ。
        ページ間でサーバー負荷軽減のためスリープを挟む。
        """
        page = 1
        while True:
            records, total_pages = self.get_kyujin_page(data_id, page)
            for record in records:
                yield record

            if page >= total_pages:
                break
            page += 1
            time.sleep(REQUEST_INTERVAL_SEC)


def _text(parent: ET.Element, tag: str) -> str:
    el = parent.find(tag)
    return el.text if el is not None and el.text else ""
