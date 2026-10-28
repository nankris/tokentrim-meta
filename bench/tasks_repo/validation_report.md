# Task validation report

Python: 3.13.5

Command: `python -m unittest discover -s tests -q`

Each state ran in a fresh isolated copy. Solution overlays and test hashes were checked.

| Task | Category | Difficulty | Before | After | Tests | Seconds (both) | Result |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| t01_escaped_fields | bug_fix | easy | FAIL | PASS | 2 | 0.089 | PASS |
| t02_month_rollover | bug_fix | easy | FAIL | PASS | 2 | 0.091 | PASS |
| t03_invoice_rounding | bug_fix | easy | FAIL | PASS | 2 | 0.083 | PASS |
| t04_falsey_cache | bug_fix | easy | FAIL | PASS | 2 | 0.080 | PASS |
| t05_cli_separator | bug_fix | easy | FAIL | PASS | 2 | 0.074 | PASS |
| t06_unicode_counts | bug_fix | easy | FAIL | PASS | 2 | 0.085 | PASS |
| t07_interval_union | bug_fix | easy | FAIL | PASS | 2 | 0.077 | PASS |
| t08_config_isolation | bug_fix | easy | FAIL | PASS | 2 | 0.078 | PASS |
| t09_ttl_boundary | bug_fix | medium | FAIL | PASS | 2 | 0.081 | PASS |
| t10_stable_priority | bug_fix | medium | FAIL | PASS | 2 | 0.083 | PASS |
| t11_csv_records | bug_fix | medium | FAIL | PASS | 2 | 0.081 | PASS |
| t12_retry_budget | bug_fix | medium | FAIL | PASS | 3 | 0.077 | PASS |
| t13_nested_lookup | bug_fix | medium | FAIL | PASS | 2 | 0.081 | PASS |
| t14_stream_windows | bug_fix | medium | FAIL | PASS | 2 | 0.084 | PASS |
| t15_dependency_order | bug_fix | hard | FAIL | PASS | 3 | 0.207 | PASS |
| t16_transaction_rollback | bug_fix | hard | FAIL | PASS | 2 | 0.078 | PASS |
| t17_query_pairs | feature | easy | FAIL | PASS | 2 | 0.084 | PASS |
| t18_chunk_batches | feature | easy | FAIL | PASS | 2 | 0.076 | PASS |
| t19_slug_suffix | feature | easy | FAIL | PASS | 2 | 0.078 | PASS |
| t20_ordered_grouping | feature | easy | FAIL | PASS | 2 | 0.074 | PASS |
| t21_json_merge_patch | feature | medium | FAIL | PASS | 2 | 0.079 | PASS |
| t22_business_days | feature | medium | FAIL | PASS | 2 | 0.087 | PASS |
| t23_lru_capacity | feature | medium | FAIL | PASS | 2 | 0.075 | PASS |
| t24_inventory_reservations | feature | medium | FAIL | PASS | 2 | 0.077 | PASS |
| t25_config_interpolation | feature | hard | FAIL | PASS | 2 | 0.074 | PASS |
| t26_route_matching | feature | hard | FAIL | PASS | 3 | 0.080 | PASS |
| t27_temperature_api | refactor | easy | FAIL | PASS | 2 | 0.079 | PASS |
| t28_sales_pipeline | refactor | medium | FAIL | PASS | 3 | 0.075 | PASS |
| t29_export_dispatch | refactor | medium | FAIL | PASS | 2 | 0.079 | PASS |
| t30_validation_errors | refactor | medium | FAIL | PASS | 2 | 0.081 | PASS |
| t31_job_transitions | refactor | medium | FAIL | PASS | 2 | 0.076 | PASS |
| t32_expression_parser | refactor | hard | FAIL | PASS | 2 | 0.077 | PASS |
| t33_timeout_cli | multi_file | medium | FAIL | PASS | 2 | 0.080 | PASS |
| t34_tagged_records | multi_file | medium | FAIL | PASS | 2 | 0.081 | PASS |
| t35_framed_stream | multi_file | hard | FAIL | PASS | 3 | 0.079 | PASS |
| t36_ledger_transfers | multi_file | hard | FAIL | PASS | 3 | 0.083 | PASS |
| t37_run_length_codec | test_driven | easy | FAIL | PASS | 2 | 0.077 | PASS |
| t38_histogram_bins | test_driven | easy | FAIL | PASS | 2 | 0.076 | PASS |
| t39_prefix_suggestions | test_driven | medium | FAIL | PASS | 2 | 0.074 | PASS |
| t40_weighted_paths | test_driven | hard | FAIL | PASS | 3 | 0.075 | PASS |

Validation: 40/40 tasks fail-before and pass-after; 0 errors.
