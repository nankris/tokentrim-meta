# Public data used by the public-benchmark slices (downloaded 2026-10-31; NOT vendored in this repo)

| dataset | source | version pinned | license | files used |
|---|---|---|---|---|
| BFCL v3 (Berkeley Function Calling Leaderboard) | https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard | HF revision `61fc0608cfd831fcfbbaa676ebdfef0ed963eeda` (lastModified 2026-04-29) | Apache-2.0 (dataset card `license: apache-2.0`) | `BFCL_v3_live_multiple.json`, `BFCL_v3_multiple.json`, `BFCL_v3_parallel_multiple.json`, `BFCL_v3_live_parallel_multiple.json` + the same names under `possible_answer/` |
| BFCL official AST checker (reference only, for the differential test) | https://github.com/ShishirPatil/gorilla `berkeley-function-call-leaderboard/bfcl_eval/eval_checker/ast_eval/ast_checker.py` | commit `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (2026-03-23) | Apache-2.0 | run unmodified from a local copy with stubbed imports; not copied into TokenTrim |
| LogChunks (Brandt, Panichella, Beller, MSR 2020) | https://zenodo.org/records/3632351 (DOI 10.5281/zenodo.3632351) | v1.0.0, `LogChunks.zip` md5 `aafa45079bdae44e340f4474ca5c4340` | CC-BY-4.0 | `build-failure-reason/*/*.xml` (labelled chunks), `logs/**/failed/*.log` (797 real Travis CI logs) |

Attribution: Brandt, C., Panichella, A., & Beller, M. (2020). *LogChunks: A Data Set for Build Log Analysis*
(Version 1.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.3632351 (CC-BY-4.0).
BFCL: Yan, Mao, Ji, Zhang, Patil, Stoica, Gonzalez, *Berkeley Function Calling Leaderboard* (2024), Apache-2.0.

Reproduce the download:
```bash
B=https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard/resolve/61fc0608cfd831fcfbbaa676ebdfef0ed963eeda
mkdir -p $BFCL_DIR/possible_answer && for f in live_multiple multiple parallel_multiple live_parallel_multiple; do
  curl -sSL -o $BFCL_DIR/BFCL_v3_$f.json $B/BFCL_v3_$f.json
  curl -sSL -o $BFCL_DIR/possible_answer/BFCL_v3_$f.json $B/possible_answer/BFCL_v3_$f.json; done
curl -sSL -o LogChunks.zip https://zenodo.org/api/records/3632351/files/LogChunks.zip/content && unzip LogChunks.zip
```
Defaults: `BFCL_DIR=/workspace/pubdata/bfcl`, `LOGCHUNKS_DIR=/workspace/pubdata/logchunks/LogChunks`.

Upstream quirk handled: BFCL `live_multiple` has one id mismatch between questions and answers
(`live_multiple_1052-79-0` vs `live_multiple_1052-279-0`); items are joined on the index before the first `-`.

## Why not SWE-bench Lite / Terminal-Bench
Both grade by running the repository's tests inside per-task Docker images. This box has no Docker or Podman, and
the images are many GB per task, so the official harness is not feasible here. File-reading SWE-bench variants
would not test tool-output compression either: TokenTrim leaves source files (plain text) uncompressed by design.
Substitute: LogChunks, i.e. REAL CI build logs with human-labelled failure reasons, which is exactly the
tool-output type TokenTrim compresses.
