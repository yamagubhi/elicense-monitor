import os
import json
import requests
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


# ========================================
# 基本設定
# ========================================

URL = "https://www.e-license.jp/el32/mSg1DWxRvAI-brGQYS-1OA%3D%3D"

LOGIN_ID = os.environ["ELICENSE_LOGIN_ID"]
LOGIN_PASSWORD = os.environ["ELICENSE_LOGIN_PASSWORD"]

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

STATE_FILE = Path("state.json")


# ========================================
# Discord通知
# ========================================

def send_discord(message):

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=15
        )

        if response.status_code in (200, 204):

            print("Discord送信成功")
            return True

        else:

            print("Discord送信失敗")
            print("ステータスコード:", response.status_code)
            print("レスポンス:", response.text)

            return False

    except Exception as e:

        print("Discord送信エラー:", e)

        return False


# ========================================
# 通知済み予約枠の読み込み
# ========================================

def load_state():

    if not STATE_FILE.exists():

        return {
            "notified": []
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            "state.json読み込みエラー:",
            e
        )

        return {
            "notified": []
        }


# ========================================
# 通知済み予約枠の保存
# ========================================

def save_state(notified):

    data = {
        "notified": [
            list(key)
            for key in notified
        ]
    }

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ========================================
# e-license予約確認
# ========================================

def check_reservations():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:

            # ----------------------------
            # ログイン画面
            # ----------------------------

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000
            )

            print(
                "ログイン画面を開きました"
            )

            inputs = page.locator(
                'input:not([type="hidden"]):visible'
            )

            if inputs.count() < 2:

                raise Exception(
                    "ログイン入力欄を取得できませんでした"
                )

            # ----------------------------
            # ID / パスワード
            # ----------------------------

            inputs.nth(0).fill(
                LOGIN_ID
            )

            inputs.nth(1).fill(
                LOGIN_PASSWORD
            )

            print(
                "ログイン情報を入力しました"
            )

            # ----------------------------
            # ログイン
            # ----------------------------

            page.get_by_role(
                "button",
                name="ログイン"
            ).click()

            page.wait_for_load_state(
                "networkidle"
            )

            page.wait_for_timeout(
                1500
            )

            print(
                "ログインしました"
            )

            print(
                "URL:",
                page.url
            )

            # ----------------------------
            # 予約可能枠
            # ----------------------------

            links = page.locator(
                "a.simei"
            )

            raw_count = links.count()

            print(
                "HTML上のsimei数:",
                raw_count
            )

            reservations = {}

            # ----------------------------
            # 空き枠情報取得
            # ----------------------------

            for i in range(raw_count):

                link = links.nth(i)

                yoyaku = link.get_attribute(
                    "data-yoyaku"
                )

                reservation_time = (
                    link.get_attribute(
                        "data-time"
                    )
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

                # 同じ予約枠を識別するキー
                key = (
                    yoyaku,
                    reservation_time,
                    zigen
                )

                # responsive tableによる
                # HTML上の重複を自動除外
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


# ========================================
# メイン処理
# ========================================

print("")

print(
    "========================================"
)

print(
    "🚗 技能予約チェック"
)

print(
    "========================================"
)

now = datetime.now()

print(
    "チェック開始:",
    now.strftime(
        "%Y/%m/%d %H:%M:%S"
    )
)


# ========================================
# 前回までの通知済み枠
# ========================================

state = load_state()

notified_reservations = {

    tuple(key)

    for key in state.get(
        "notified",
        []
    )
}


try:

    # ====================================
    # 現在の予約枠を取得
    # ====================================

    reservations = (
        check_reservations()
    )

    current_keys = set(
        reservations.keys()
    )

    print("")

    print(
        "現在の予約可能枠:",
        len(reservations),
        "件"
    )


    # ====================================
    # 新しく出現した予約枠
    # ====================================

    new_reservations = []

    for (
        key,
        reservation
    ) in reservations.items():

        if (
            key
            not in notified_reservations
        ):

            new_reservations.append(
                (
                    key,
                    reservation
                )
            )


    # ====================================
    # 新規予約枠がある場合
    # ====================================

    if new_reservations:

        print("")

        print(
            "🟢 新しい予約枠を発見しました！"
        )

        message = (
            "🚨 **技能予約に空きが出ました！** 🚨\n"
        )

        for (
            key,
            reservation
        ) in new_reservations:

            print(
                reservation["date"],
                reservation["week"],
                reservation["time"],
                f"（{reservation['zigen']}限）"
            )

            message += (

                "\n"

                f"🟢 **"
                f"{reservation['date']}"
                f"{reservation['week']}"
                f"**\n"

                f"⏰ **"
                f"{reservation['time']}"
                f"**\n"

                f"🚗 "
                f"{reservation['zigen']}"
                f"限\n"
            )

        message += (
            "\n⚡ 予約サイトを確認してください！"
        )


        # =================================
        # Discord通知
        # =================================

        if send_discord(
            message
        ):

            # 通知成功した枠だけ
            # 通知済みに追加

            for (
                key,
                reservation
            ) in new_reservations:

                notified_reservations.add(
                    key
                )

        else:

            print(
                "Discord通知に失敗したため、"
                "通知済みには登録しません。"
            )


    else:

        print(
            "新しい予約枠はありません。"
        )


    # ====================================
    # 消えた予約枠を通知済みから削除
    #
    # これにより、
    #
    # 空き発生
    # ↓
    # 通知
    # ↓
    # 埋まる
    # ↓
    # 再び空く
    #
    # の場合に再通知される
    # ====================================

    notified_reservations.intersection_update(
        current_keys
    )


    # ====================================
    # 状態保存
    # ====================================

    save_state(
        notified_reservations
    )


    print("")

    print(
        "通知済み予約枠:",
        len(notified_reservations),
        "件"
    )

    print(
        "チェック完了"
    )


except Exception as e:

    print("")

    print(
        "⚠️ チェック中にエラー発生"
    )

    print(e)

    raise
