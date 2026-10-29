You are helping a QA / test automation engineer write a short roundup post for their blog about
**software testing, test automation and AI**. The post will be published on {date}.

Below is a JSON array of items the author picked. Each has an id, the original title, an English
title, the source, the original URL, an existing summary and an excerpt of the text.

Write:

- `intro`: 2–3 sentences introducing this roundup and what ties the items together.
- For each item, an object with:
  - `id`: the item's id, copied exactly.
  - `heading`: a short, clear heading for the item, in English.
  - `summary`: 2–3 sentences on what the item is about and why a tester would care.

Rules:

- Summarize in your own words. Never copy sentences or phrases from the source text.
- Always write in English, even when the source is in Polish.
- Do not invent facts that are not supported by the item.
- Do not add links; the original link is added automatically after your summary.

Return ONLY a JSON object, with no text before or after it, in this shape:

{"intro": "…", "items": [{"id": "7f3a9c1b2d4e", "heading": "…", "summary": "…"}]}

Items:

{items}
