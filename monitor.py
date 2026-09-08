import os
import json
import requests
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright


# ==========================================
# 設定
# ==========================================

URL = "https://www.e-license.jp/el32/mSg1DWxRvAI-brGQYS-1OA%3D%3D"

LOGIN_ID = os.environ["ELICENSE_LOGIN_ID"]
LOGIN_PASSWORD = os.environ["ELICENSE_LOGIN_PASSWORD"]

CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
USER_ID = os.environ["LINE_USER_ID"]

STATE_FILE = Path("state.json")


# ==========================================
# LINE送信
# ==========================================

def send_line(message):

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    data = {
        "to": USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=15
        )

        if response.status_code == 200:

            print("LINE送信成功")
            return True

        else:

            print("LINE送信失敗")
            print("ステータスコード:", response.status_code)
            print("レスポンス:", response.text)

            return False

    except Exception as e:

        print("LINE送信エラー:", e)
        return False


# ==========================================
# 前回の状態を読み込む
# ==========================================

def load_state():

    if not STATE_FILE.exists():
        return {
            "notified": [],
            "check_count": 0
        }

    try:

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:

        return {
            "notified": [],
            "check_count": 0
        }


# ==========================================
# 状態を保存
# ==========================================

def save_state(notified, check_count):

    data = {
        "notified": [
            list(key)
            for key in notified
        ],
        "check_count": check_count
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ==========================================
# 予約枠を1回チェック
# ==========================================

def check_reservations():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:

            # ログイン画面
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000
            )

            print("ログイン画面を開きました")

            # ID・パスワード
            inputs = page.locator(
                'input:not([type="hidden"]):visible'
            )

            if inputs.count() < 2:
                raise Exception(
                    "ログイン入力欄を取得できませんでした"
                )

            inputs.nth(0).fill(LOGIN_ID)
            inputs.nth(1).fill(LOGIN_PASSWORD)

            print("ログイン情報を入力しました")

            # ログイン
            page.get_by_role(
                "button",
                name="ログイン"
            ).click()

            page.wait_for_load_state(
                "networkidle"
            )

            page.wait_for_timeout(1500)

            print("ログインしました")
            print("URL:", page.url)

            # 空き枠取得
            links = page.locator("a.simei")

            raw_count = links.count()

            print("HTML上のsimei数:", raw_count)

            # 重複除去
            reservations = {}

            for i in range(raw_count):

                link = links.nth(i)

                yoyaku = link.get_attribute(
                    "data-yoyaku"
                )

                reservation_time = link.get_attribute(
                    "data-time"
                )

                zigen = link.get_attribute(
                    "data-zigen"
                )

                date = link.get_attribute(
                    "data-date"
                )

                week = link.get_attribute(
                    "data-week"
                )

                key = (
                    yoyaku,
                    reservation_time,
                    zigen
                )

                reservations[key] = {
                    "date": date,
                    "week": week,
                    "time": reservation_time,
                    "zigen": zigen,
                    "yoyaku": yoyaku
                }

            return reservations

        finally:

            browser.close()


# ==========================================
# メイン処理
# ==========================================

print("")
print("========================================")
print("🚗 技能予約チェック")
print("========================================")

now = datetime.now()

print(
    "チェック開始:",
    now.strftime("%Y/%m/%d %H:%M:%S")
)


state = load_state()

notified_reservations = {
    tuple(key)
    for key in state.get("notified", [])
}

check_count = state.get(
    "check_count",
    0
)

check_count += 1


try:

    reservations = check_reservations()

    current_keys = set(
        reservations.keys()
    )

    print("")
    print(
        "現在の予約可能枠:",
        len(reservations),
        "件"
    )


    # ======================================
    # 新しい予約枠
    # ======================================

    new_reservations = []

    for key, reservation in reservations.items():

        if key not in notified_reservations:

            new_reservations.append(
                (key, reservation)
            )


    if new_reservations:

        print("")
        print("新しい予約枠を発見しました！")

        message = (
            "🚗 技能予約に空きが出ました！\n"
        )

        for key, reservation in new_reservations:

            print(
                reservation["date"],
                reservation["week"],
                reservation["time"],
                f"（{reservation['zigen']}限）"
            )

            message += (
                "\n"
                f"🟢 {reservation['date']}"
                f"{reservation['week']}\n"
                f"⏰ {reservation['time']}\n"
                f"🚗 {reservation['zigen']}限\n"
            )

        message += (
            "\n予約サイトを確認してください！"
        )

        if send_line(message):

            for key, reservation in new_reservations:
                notified_reservations.add(key)

    else:

        print("新しい予約枠はありません。")


    # ======================================
    # 消えた枠は通知済みから削除
    # ======================================

    notified_reservations.intersection_update(
        current_keys
    )


    # ======================================
    # 約1時間ごとの生存通知
    # 5分 × 12回 = 約1時間
    # ======================================

    if check_count >= 12:

        if len(reservations) == 0:

            status_message = (
                "🚗 技能予約監視中\n\n"
                "現在、新しい予約可能枠はありません。\n\n"
                "監視は正常に継続しています。"
            )

        else:

            status_message = (
                "🚗 技能予約監視中\n\n"
                f"現在、予約可能枠は"
                f"{len(reservations)}件あります。\n"
                "すべて通知済みの枠です。\n\n"
            )

            for reservation in reservations.values():

                status_message += (
                    f"・{reservation['date']}"
                    f"{reservation['week']} "
                    f"{reservation['time']} "
                    f"({reservation['zigen']}限)\n"
                )

            status_message += (
                "\n監視は正常に継続しています。"
            )

        if send_line(status_message):
            check_count = 0


    save_state(
        notified_reservations,
        check_count
    )

    print("")
    print("チェック完了")


except Exception as e:

    print("")
    print("⚠️ チェック中にエラー発生")
    print(e)

    raise
