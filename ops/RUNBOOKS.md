# Failure Runbooks

## Live Site Is Broken

1. Run the live deployment health check.
2. Identify whether the failure is root mirror, DNS, missing asset, or bad HTML.
3. Revert the last public-site commit or restore the last known-good branch.
4. Re-run the live health check.

## Wrong Menu Is Published

1. Archive the affected menu immediately.
2. Notify the owner manually if the page was shared.
3. Correct the draft from owner-confirmed data.
4. Re-publish and verify the live URL.

## Email Sent To Wrong Recipient

1. Stop the batch.
2. Mark the affected lead for manual review.
3. Record the incident in the internal audit log.
4. Do not send follow-up unless the owner replies.

## Owner Requests Takedown

1. Archive the menu.
2. Remove public links to the page.
3. Keep a minimal internal support record.
4. Confirm manually that the public URL no longer shows the active menu.

## Email Provider Fails

1. Do not mark messages as sent.
2. Check provider error and domain status.
3. Keep records in manual review.
4. Retry only after the provider problem is resolved.
