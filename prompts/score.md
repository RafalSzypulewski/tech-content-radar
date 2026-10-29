You are helping curate a reading list about **software testing, test automation, AI and technology**
for a QA / test automation engineer who writes a blog for other testers and developers.

Below is a JSON array of collected items (blog posts, videos, podcasts, releases, community links).
For each item, judge it from its title, type, source and text, then return one result object.

Write all output in English, even when the source is in Polish.

For every item return:

- `id`: the item's id, copied exactly.
- `title_en`: the title in English (translate it if the original is not English; otherwise keep it).
- `summary_en`: 2–3 sentences saying what the item is about and what a reader would learn.
  Use your own words; do not copy sentences from the text.
- `relevance`: integer 1–10. How relevant it is to software testing, test automation, QA,
  AI in testing, or practical AI / software engineering. 10 = squarely about testing or test
  automation; 5 = general software engineering or AI that a tester might find useful;
  1 = off-topic (e.g. politics, hardware, unrelated news that only mentions a keyword).
- `quality`: integer 1–10. Depth, originality and practical value. Low for thin link posts,
  marketing, announcements with no substance, or clickbait. If the text is only a title,
  judge cautiously and stay near the middle.
- `reason`: at most 25 words explaining the scores.
- `tags`: 1–3 tags chosen only from this list: {tags}

Return ONLY a JSON array, one object per input item, with no text before or after it. Example shape:

[{"id": "7f3a9c1b2d4e", "title_en": "…", "summary_en": "…", "relevance": 8, "quality": 7, "reason": "…", "tags": ["test-automation", "tutorial"]}]

Items:

{items}
