# REAL Meta Model API run v3 — 2026-10-30

Model `muse-spark-1.3-contributor` on https://api.meta.ai/v1 (**Contributor tier: Meta may use the request content for training; the user consented**). 20 tasks x 6 modes x 3 repeats = 360 complete runs; spend $1.9776 (main) + $1.0199 (v3b layout-only modes, a second invocation run right after the main one). Usage and dollars come from the API `usage` fields priced with `tokentrim/prices.toml`.

## Per mode

| Mode | Client input | Runs | Pass (run-level) [Wilson 95%] | Pass (task-level, n=tasks) [Wilson 95%] | Mean $/run | Mean prompt tok/run | Cached share of prompt | Calls with any cache hit | Mean $/run if no cache hits |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | well-behaved (sorted tools, no volatile text) | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00802 | 78,421 | 12.3% | 12% | 0.00897 |
| baseline-ts | volatile timestamp + request id on system line 2 | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00906 | 79,619 | 0.4% | 0% | 0.00909 |
| baseline-tools | set-ordered tools + dict-order nondeterminism (re-drawn when tool set changes) | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00822 | 79,118 | 11.8% | 12% | 0.00914 |
| tokentrim | naive (timestamp + set-ordered tools) -> TokenTrim v3 defaults | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00766 | 68,235 | 4.0% | 5% | 0.00793 |
| layout-move | naive -> cache_layout only; volatile lines moved to a trailing message (v3b) | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00885 | 79,422 | 2.4% | 3% | 0.00904 |
| layout-drop | naive -> cache_layout only; volatile lines dropped (v3b) | 60 | 100.0% [94.0, 100.0] | 100.0% [83.9, 100.0] | 0.00814 | 78,652 | 10.5% | 12% | 0.00895 |

## Paired comparisons (repeats averaged per task, paired bootstrap over tasks, 2,000 resamples, seed 42)

Saving = (reference - new) / reference, so positive means `new` is cheaper. Pass diff = new - reference.

| New vs reference | Billed $ saving [95% CI] | Prompt-token saving [95% CI] | $ saving if no cache hits [95% CI] | Pass diff pp, bootstrap [95% CI] | Pass diff pp, Newcombe task-level [95% CI] | Non-inferior at -10 pp? |
|---|---:|---:|---:|---:|---:|:-:|
| tokentrim vs baseline-ts | +15.5% [+14.0, +17.0] | +14.3% [+13.4, +15.2] | +12.8% [+11.8, +13.9] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| tokentrim vs baseline-tools | +6.8% [+3.2, +10.7] | +13.8% [+12.6, +15.1] | +13.3% [+12.0, +14.9] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| tokentrim vs baseline | +4.5% [+2.2, +6.6] | +13.0% [+12.3, +13.7] | +11.6% [+10.4, +12.7] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| baseline-ts vs baseline | -13.0% [-15.4, -10.7] | -1.5% [-2.5, -0.7] | -1.4% [-2.4, -0.4] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| baseline-tools vs baseline | -2.5% [-6.5, +1.2] | -0.9% [-2.4, +0.4] | -1.9% [-5.1, +0.2] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| layout-move vs baseline-ts | +2.3% [+0.3, +4.5] | +0.2% [-1.3, +1.7] | +0.5% [-0.9, +1.9] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| layout-drop vs baseline-ts | +10.1% [+7.9, +12.4] | +1.2% [+0.2, +2.3] | +1.5% [+0.6, +2.6] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| layout-move vs baseline | -10.4% [-13.5, -7.6] | -1.3% [-2.5, -0.1] | -0.8% [-2.2, +0.4] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| layout-drop vs baseline | -1.6% [-5.0, +1.9] | -0.3% [-1.3, +0.6] | +0.2% [-1.2, +1.5] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |
| tokentrim vs layout-move | +13.5% [+11.8, +15.4] | +14.1% [+13.2, +15.0] | +12.4% [+11.1, +13.7] | +0.0 [+0.0, +0.0] | +0.0 [-16.1, +16.1] | no (interval too wide or below margin) |

## Pass-rate guard (eager prune is the default; any task where tokentrim passed fewer repeats than a baseline is flagged)

- No task where tokentrim passed fewer repeats than any baseline.

## Per task (passes out of repeats; mean billed $ per run)

| Task | baseline | baseline-ts | baseline-tools | tokentrim | layout-move | layout-drop |
|---|---|---|---|---|---|---|
| t01_escaped_fields | 3/3 $0.00800 | 3/3 $0.00828 | 3/3 $0.00768 | 3/3 $0.00713 | 3/3 $0.00842 | 3/3 $0.00686 |
| t03_invoice_rounding | 3/3 $0.00797 | 3/3 $0.00913 | 3/3 $0.00776 | 3/3 $0.00687 | 3/3 $0.00773 | 3/3 $0.00821 |
| t05_cli_separator | 3/3 $0.00776 | 3/3 $0.00894 | 3/3 $0.00815 | 3/3 $0.00722 | 3/3 $0.00862 | 3/3 $0.00783 |
| t07_interval_union | 3/3 $0.00744 | 3/3 $0.00865 | 3/3 $0.00894 | 3/3 $0.00677 | 3/3 $0.00874 | 3/3 $0.00838 |
| t09_ttl_boundary | 3/3 $0.00737 | 3/3 $0.00874 | 3/3 $0.00714 | 3/3 $0.00789 | 3/3 $0.00855 | 3/3 $0.00870 |
| t11_csv_records | 3/3 $0.00880 | 3/3 $0.00987 | 3/3 $0.01086 | 3/3 $0.00830 | 3/3 $0.00946 | 3/3 $0.00844 |
| t13_nested_lookup | 3/3 $0.00782 | 3/3 $0.00877 | 3/3 $0.00800 | 3/3 $0.00773 | 3/3 $0.00845 | 3/3 $0.00835 |
| t15_dependency_order | 3/3 $0.00863 | 3/3 $0.00921 | 3/3 $0.00883 | 3/3 $0.00802 | 3/3 $0.00921 | 3/3 $0.00893 |
| t17_query_pairs | 3/3 $0.00744 | 3/3 $0.00862 | 3/3 $0.00807 | 3/3 $0.00754 | 3/3 $0.00862 | 3/3 $0.00766 |
| t19_slug_suffix | 3/3 $0.00710 | 3/3 $0.00901 | 3/3 $0.00741 | 3/3 $0.00760 | 3/3 $0.00871 | 3/3 $0.00783 |
| t21_json_merge_patch | 3/3 $0.00788 | 3/3 $0.00901 | 3/3 $0.00722 | 3/3 $0.00769 | 3/3 $0.00872 | 3/3 $0.00841 |
| t23_lru_capacity | 3/3 $0.00751 | 3/3 $0.00833 | 3/3 $0.00768 | 3/3 $0.00709 | 3/3 $0.00828 | 3/3 $0.00778 |
| t25_config_interpolation | 3/3 $0.00949 | 3/3 $0.01032 | 3/3 $0.00917 | 3/3 $0.00872 | 3/3 $0.00982 | 3/3 $0.00860 |
| t27_temperature_api | 3/3 $0.00831 | 3/3 $0.00915 | 3/3 $0.00894 | 3/3 $0.00782 | 3/3 $0.00906 | 3/3 $0.00836 |
| t29_export_dispatch | 3/3 $0.00832 | 3/3 $0.00922 | 3/3 $0.00852 | 3/3 $0.00777 | 3/3 $0.00928 | 3/3 $0.00882 |
| t31_job_transitions | 3/3 $0.00814 | 3/3 $0.00876 | 3/3 $0.00777 | 3/3 $0.00770 | 3/3 $0.00933 | 3/3 $0.00718 |
| t33_timeout_cli | 3/3 $0.00891 | 3/3 $0.00947 | 3/3 $0.00796 | 3/3 $0.00800 | 3/3 $0.00946 | 3/3 $0.00844 |
| t35_framed_stream | 3/3 $0.00848 | 3/3 $0.00965 | 3/3 $0.00805 | 3/3 $0.00816 | 3/3 $0.00851 | 3/3 $0.00850 |
| t37_run_length_codec | 3/3 $0.00744 | 3/3 $0.00917 | 3/3 $0.00835 | 3/3 $0.00737 | 3/3 $0.00932 | 3/3 $0.00827 |
| t39_prefix_suggestions | 3/3 $0.00758 | 3/3 $0.00893 | 3/3 $0.00790 | 3/3 $0.00782 | 3/3 $0.00881 | 3/3 $0.00732 |

Calls: 2895; reasoning tokens 1,841,053 of 2,030,343 completion tokens; calls ending `length`: 1246; retries: 32.

What these numbers do NOT measure: the split of TokenTrim's saving between cache_layout and eager prune in the main run; the v3b layout-only modes were run separately and no prune-only mode was run, so `tokentrim vs layout-move` is an approximate prune+trim effect); other models; real agents (the agent is scripted).

## Route pilot (3 tasks, 1 pass): Wonder only vs Spark-first with sticky escalation to Wonder

`pilot-wonder`: `muse-wonder-1.0` for every call, no savers. `pilot-sparkfirst`: all savers, `CheapFirstRouter` on Standard `muse-spark-1.3` (not Contributor), sticky escalation to Wonder on visible test failure / malformed output / no progress.

| Task | Wonder $ | Wonder pass | Spark-first $ | Spark-first pass | Spark-first escalated? | Models used (Spark-first) |
|---|---:|:-:|---:|:-:|:-:|---|
| t07_interval_union | 0.2988 | ✓ | 0.0952 | ✓ | no | muse-spark-1.3 |
| t15_dependency_order | 0.2986 | ✓ | 0.0913 | ✓ | no | muse-spark-1.3 |
| t21_json_merge_patch | 0.3564 | ✓ | 0.1014 | ✓ | no | muse-spark-1.3 |
| **total** | **0.9538** | 3/3 | **0.2879** | 3/3 | | |

Pilot spend $1.2417 (sub-cap $3). Three tasks, one pass: a direction check, not an estimate.

