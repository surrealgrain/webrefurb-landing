# WebRefurb Outreach Launch Checklist

## Pre-Send Checks

- Confirm `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_FROM_NAME`, and optional `RESEND_REPLY_TO_EMAIL` are set.
- Open the dashboard and preview each lead before sending.
- Confirm the recipient email, restaurant name, website, address, menu evidence URLs, and status.
- Send one test email to your own inbox and check subject, sender name, reply-to, footer link, inline images, and PDF attachment names.
- Confirm the email footer visibly shows `webrefurb.com` and links to `https://webrefurb.com/ja`.
- Do not send machine-only leads. Leave them as `needs_review`.

## First 5 To 10 Email Batch

- Start with 5 to 10 high-confidence ramen or izakaya leads only.
- Prefer leads with official menu evidence, clear Japanese-only menu content, and no strong chain indicators.
- Avoid leads with uncertain category, weak evidence, missing source URL, or unclear business status.
- Send slowly from the dashboard and wait for each send confirmation.
- After sending, refresh the dashboard and confirm sent leads no longer appear in the active queue.

## Monitor After Sending

- Watch replies in the sending mailbox.
- Check Resend for bounces, rejected sends, spam complaints, or domain authentication warnings.
- Record any bounced or invalid addresses as `bounced` or `invalid` before future searches.
- Record opt-outs immediately as `do_not_contact`.
- Keep notes on which evidence patterns produce good replies.

## Replies

- Reply manually and naturally from the same sender identity.
- Ask for current menu photos or PDFs, ticket-machine photos if applicable, and any menu notes.
- Do not mention AI, automation, scraping, or internal tools in customer-facing replies.
- Mark the lead `replied` after a real reply thread starts.
- Mark the lead `converted` only after the customer commits to paid work.

## Bounces And Do Not Contact

- If an email bounces, mark the lead `bounced`.
- If the address is clearly wrong, mark it `invalid`.
- If the restaurant opts out or says no, mark it `do_not_contact`.
- Do not re-send to `sent`, `replied`, `converted`, `bounced`, `invalid`, `skipped`, `needs_review`, or `do_not_contact` leads.

## Duplicate Avoidance

- Before each batch, search from the dashboard so place ID, domain, phone, email, and name plus area matching can exclude existing records.
- Do not rely on name-only matching. Separate shops can share names.
- Review duplicate skips in search results if the batch looks unexpectedly small.
- Test sends to your own inbox should not mark a restaurant as sent.
- Failed sends should not mark a restaurant as sent.

## Backup And Export

- Back up the `state/` directory before the first real batch and after every outreach session.
- Keep copies of `state/leads/`, `state/sent/`, `state/jobs/`, and `state/uploads/` if custom builds were created.
- Export lead and sent records before any large cleanup.
- Keep `.env` out of git and never share it in screenshots or logs.
