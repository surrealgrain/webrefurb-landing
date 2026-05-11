# Owner Journey

## Cold Lead To Reply

1. Lead is discovered and normalized as ramen or izakaya.
2. Contact route is approved only if it is email or a supported contact form.
3. First contact links the generic demo and asks for a reply only.
4. No price, menu-photo request, attachment, or lead-specific sample appears in first contact.

## Reply To Trial

1. Owner replies with interest or a question.
2. Operator answers manually.
3. If the owner wants a trial, create a trial record with status `requested`.
4. After the owner agrees to proceed, move to `accepted` or `intake_needed`.
5. Intake asks only for what is needed after the reply: current menu source, restaurant public name, price/tax policy, allergy policy, and contact email.

## Trial Build

1. Extract menu items from owner-provided material.
2. Translate and structure the menu.
3. Generate draft QR menu and QR sign.
4. Send owner review.
5. Block publish until owner confirms prices, descriptions, ingredients, and allergy notes.
6. Move to `live_trial` for the 7-day trial.

## Trial Outcome

- If the owner continues, move to `converted`, issue invoice, and keep the paid page live.
- If the owner declines, move to `declined`, then archive the page.
- If no decision is made after follow-up, archive after manual review.
