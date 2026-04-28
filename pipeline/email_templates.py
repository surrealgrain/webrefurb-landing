"""Locked email templates for cold outreach.

Single universal template for all business types (ramen, izakaya, etc.).
The only variable is {店名} (business name).
"""

# ---------------------------------------------------------------------------
# Subject line
# ---------------------------------------------------------------------------

SUBJECT = "英語メニュー制作のご提案（{店名}様）"

# ---------------------------------------------------------------------------
# Body template
# ---------------------------------------------------------------------------

BODY = """{店名} ご担当者様

突然のご連絡にて失礼いたします。
飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。

海外からのお客様へのご案内が少しでもスムーズになるよう、英語メニュー制作のお手伝いができればと思い、ご連絡いたしました。

添付のサンプルは、デザインや仕上がりのイメージをご覧いただくためのものです。
実際に制作する際は、貴店のメニュー内容に合わせて作成いたします。

ご興味がございましたら、現在お使いのメニューのお写真をお送りください。
ご確認用のサンプルを作成し、お送りいたします。

ラミネート加工および店舗への直接のお届けも承っております。

ご検討いただけますと幸いです。
どうぞよろしくお願いいたします。

Chris（クリス）"""

# ---------------------------------------------------------------------------
# Toggleable lines
# ---------------------------------------------------------------------------

LINE_INPERSON = "ラミネート加工および店舗への直接のお届けも承っております。"

LINE_MACHINE = "券売機用の英語ガイドもあわせて作成可能です。"

# ---------------------------------------------------------------------------
# Operator-facing English editing template
# ---------------------------------------------------------------------------

ENGLISH_BODY = """Dear {store_name} team,

I hope you do not mind my sudden message.
My name is Chris, and I create English menus for restaurants.

I am reaching out because I would be happy to help make guidance for overseas customers a little smoother with an English menu.

The attached sample is intended to show the design and finished style.
When creating the actual version, I would prepare it to match your restaurant's menu content.

If you are interested, please send photos of the menu you currently use.
I will create and send a sample for your review.

Lamination and direct delivery to your restaurant are also available.

Thank you for your consideration.
I look forward to hearing from you.

Chris"""

ENGLISH_LINE_INPERSON = "Lamination and direct delivery to your restaurant are also available."

ENGLISH_LINE_MACHINE = "I can also create an English guide for your ticket machine."

# ---------------------------------------------------------------------------
# Contact-form pitch template
# ---------------------------------------------------------------------------

CONTACT_FORM_BODY = """突然のご連絡にて失礼いたします。

飲食店向けに英語メニューや注文ガイドの制作を行っております、WebRefurbのChris（クリス）と申します。

海外からのお客様へのご案内やご注文が少しでもスムーズになるよう、英語メニュー、券売機ガイド、QRコード付き英語メニューページなどの制作を行っております。

現在お使いのメニューや店内の注文方法に合わせて、印刷用データの納品、ラミネート加工、店舗へのお届けまで対応可能です。

ご興味がございましたら、現在お使いのメニューや注文案内のお写真をお送りいただけますと幸いです。
貴店の内容に合わせた英語メニュー案を作成いたします。

詳しくはこちらをご覧ください。
https://webrefurb.com/ja

ご連絡は下記メールアドレスまでお願いいたします。

[chris@webrefurb.com](mailto:chris@webrefurb.com)

どうぞよろしくお願いいたします。

Chris（クリス）"""
