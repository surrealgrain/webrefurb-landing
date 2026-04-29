"""Locked email templates for cold outreach.

Five situation-based templates keyed on the physical ordering problem
the tourist faces at that shop:

  1. ramen_menu        — ramen shop with a visible menu
  2. ramen_menu_and_machine — ramen shop with menu + ticket machine
  3. izakaya_menu      — izakaya with food and drink menu
  4. machine_only      — shop where only a ticket machine exists
  5. unknown           — generic fallback for unclear setups

The only merge variable is {店名} (business name).
"""

# ---------------------------------------------------------------------------
# Subject lines
# ---------------------------------------------------------------------------

SUBJECT = "英語注文ガイド制作のご提案（{店名}様）"
MACHINE_ONLY_SUBJECT = "英語注文ガイド制作のご提案（{店名}様）"

# ---------------------------------------------------------------------------
# Toggleable lines
# ---------------------------------------------------------------------------

LINE_INPERSON = "ラミネート加工や店舗へのお届けにも対応しております。"

LINE_MACHINE = "券売機用の英語ガイドもあわせて作成可能です。"

ENGLISH_LINE_INPERSON = "Lamination and direct delivery to your restaurant are also available."

ENGLISH_LINE_MACHINE = "I can also create an English guide for your ticket machine."

# ---------------------------------------------------------------------------
# Contact-form pitch template (separate — no attachments possible)
# ---------------------------------------------------------------------------

CONTACT_FORM_BODY = """突然のご連絡にて失礼いたします。

飲食店向けに英語の注文ガイドやメニュー資料の制作を行っております、Chris（クリス）と申します。

公開されているメニューや店舗情報を拝見し、海外からのお客様が注文時に迷いやすい箇所があるかもしれないと思いご連絡しました。

現在お使いのメニューや店内の注文方法に合わせて、印刷用データ、ラミネート済みの店頭用資料、QRコード付き英語注文メニューなどを制作できます。

ご興味がございましたら、現在お使いのメニューや注文案内のお写真をお送りいただけますと幸いです。
貴店の内容に合わせた小さな確認用サンプルを作成いたします。

詳しくはこちらをご覧ください。
https://webrefurb.com/ja

ご連絡は下記メールアドレスまでお願いいたします。

[chris@webrefurb.com](mailto:chris@webrefurb.com)

不要なご連絡でしたら「不要」とご返信ください。今後のご連絡は控えます。

どうぞよろしくお願いいたします。

Chris（クリス）"""
