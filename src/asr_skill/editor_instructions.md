Read `segments.jsonl` in this directory. If `confirmed_name_map.json` exists, those entries are caller-confirmed. Write `edited.json` here. Do not decide the text with a regular expression or a keyword list.

Acoustic labels are per file. The same letter in another file is not the same person. Do not rewrite `segments.jsonl`.

`edited.json` uses these keys: `rows`, `excluded`, `uncertain`, `corrections`, `name_map`.

Each source `segment_id` appears in exactly one of `rows`, `uncertain`, or `excluded`. An exclusion `reason` must be a non-empty string. Null, a number, a boolean, a list, or a dict is not a reason. An uncertain row may be the first, middle, or last source row. It stays in the readable CSV at that source position with `speaker` set to `unknown`. Do not drop it, and do not put every uncertain row at the end.

A row has `source_ids`, `start`, `end`, `speaker`, and `content`. `start` and `end` stay inside the source interval. Keep source time order.

If an acoustic label contains `+` and you assign one person, set `reason` to `overlap_attribution` and set `confidence`. Otherwise keep the combined label or use `unknown`.

`name_map` is filename, then acoustic label. Every label in the source appears. `status` is `mapped` or `unknown`. `mapped` has a non-empty `name`. `unknown` has an empty name. `origin` is `caller` or `editor`. Do not change a caller entry. A caller may supply a name that is not spoken. An editor name must occur in that file's source text, as a whole English token or a Chinese substring, and the entry needs `source_id` or `evidence`. This is not speaker assignment by keyword, and it is not proof of identity.

Remove fillers that carry no meaning, including a sentence-final particle that is only noise. Keep a short reply that answers, agrees, refuses, or corrects. Remove stutter that is not a second statement. Merge adjacent rows from the same acoustic speaker when they are one broken turn. Do not merge across a real speaker change. Add punctuation. Do not summarize or invent paragraphs. Keep possibility, negation, conditions, numbers, and terms.

If you change a number or a negation, add a `corrections` item with `source_ids`, `before`, `after`, and `reason`. `before` is the source token. `after` is non-empty and must appear in the exported text. Empty `after` is only for a fully excluded segment.

This check does not prove the sentences mean the same thing.
