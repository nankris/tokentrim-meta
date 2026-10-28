# TokenTrim prep (no code yet, waiting for Meta credits)

Hackathon: Meta Global AI Developer Hackathon, Oct 26 12:00 PM ET to Nov 4 9:00 PM ET. Submissions due Nov 4 9 PM ET (about 7:30 AM IST Nov 5). Judging Nov 4-8, finals Nov 9.
Credits: $150 Meta Model API credits. Claim via Google form by Nov 4 9 PM ET. Needs: Meta Model API account at dev.meta.ai, team ID from URL, card on file for first API call.

Idea: open-source middleware for coding agents (Claude Code, Codex, Muse Code): prune context and tool output, route easy steps to cheaper models, plan prompts around the cache.
Deliverable promised in the application and Substack post: 40 real repo-edit tasks, baseline vs TokenTrim, tokens + dollars + pass rate with 95% CIs, live dashboard, all open source.
Prior numbers: cost $0.186 -> $0.060 per task (-68%), 60/60 passing; front-loading cut tokens 45% but cost only 13.5%; local model offload cost ~2.1x more.

Meta Model API prices per 1M tokens (https://dev.meta.ai/docs/pricing-rate-limits):
- muse-spark-1.3: in 1.25, cached 0.15, out 4.25 (1M context)
- muse-spark-1.3-contributor: in 0.10, cached 0.002, out 0.20 (Meta may train on content)
- muse-wonder-1.0: in 4.00, cached 0.20, out 20.00
- Muse Image $0.01/image; web search $2.50 per 1,000 queries
$150 buys about 75M tokens on Spark standard (3:1 in:out), ~1.2B on contributor, ~19M on Wonder.

Rules: main ~/.codex account only (stop at 78%), model gpt-6-astra for coding; no push/post without user OK; issues-found/ folder; secret scan before any push.
Open questions for tomorrow: which 40 repos/tasks, pass-check method, Spark vs Wonder as strong model, contributor mode OK for benchmark?
