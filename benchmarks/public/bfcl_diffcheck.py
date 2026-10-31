"""Differential test: TokenTrim's BFCL AST checker vs the OFFICIAL checker (run unmodified from a local copy of
gorilla@6ea5797 ast_checker.py with its imports stubbed; the official file is not vendored here).
Inputs: the oracle output of every item plus deterministic perturbations (wrong function, dropped required
parameter, changed value, extra parameter, wrong type, case/punctuation variant that BFCL accepts, no call).
Usage: BFCL_OFFICIAL_STUB=/path/to/stub python3 -m benchmarks.public.bfcl_diffcheck
"""
import copy
import json
import os
import random
import sys

from . import bfcl as B


def perturb(item, rng):
    base = B.oracle_output(item)
    yield "oracle", base
    names = [B.oai_name(f["name"]) for f in item["function"]]
    call = base[0]
    name, args = next(iter(call.items()))
    other = [n for n in names if n != name]
    if other:
        yield "wrong_func", [{other[0]: args}] + base[1:]
    req = (next(f for f in item["function"] if B.oai_name(f["name"]) == name).get("parameters") or {}).get("required") or []
    if req and req[0] in args:
        a = dict(args); a.pop(req[0])
        yield "drop_required", [{name: a}] + base[1:]
    for k, v in args.items():
        a = copy.deepcopy(args)
        if isinstance(v, str):
            a[k] = v + "_zz"; yield "value_changed", [{name: a}] + base[1:]
            a = copy.deepcopy(args); a[k] = v.upper().replace(" ", "  "); yield "case_space_variant", [{name: a}] + base[1:]
            a = copy.deepcopy(args); a[k] = 7; yield "wrong_type", [{name: a}] + base[1:]
            break
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            a[k] = v + 1; yield "number_changed", [{name: a}] + base[1:]
            break
    a = dict(args); a["zz_extra"] = "x"
    yield "extra_param", [{name: a}] + base[1:]
    yield "no_call", []
    if len(base) > 1:
        yield "reversed_order", list(reversed(base))


def main():
    sys.path.insert(0, os.environ["BFCL_OFFICIAL_STUB"])
    from bfcl_eval.eval_checker.ast_eval.ast_checker import ast_checker
    from bfcl_eval.constants.enums import Language
    rng = random.Random(0)
    total, agree, cases = 0, 0, {}
    disagreements = []
    for cat in ["live_multiple", "multiple", "parallel_multiple", "live_parallel_multiple"]:
        for item in B.load(cat):
            for kind, out in perturb(item, rng):
                mine = B.check(item, out)[0]
                try:
                    off = ast_checker(item["function"], out, item["ground_truth"], Language.PYTHON, cat,
                                      "gpt-4o-2024-08-06-FC")["valid"]
                except Exception as exc:
                    off = f"error:{type(exc).__name__}"
                total += 1
                c = cases.setdefault(kind, [0, 0, 0])
                c[0] += 1; c[1] += mine is True; c[2] += (mine == off)
                if mine == off:
                    agree += 1
                elif len(disagreements) < 30:
                    disagreements.append({"id": item["id"], "kind": kind, "mine": mine, "official": off})
    res = {"outputs_checked": total, "agree": agree, "agreement": agree / total,
           "by_case": {k: {"n": v[0], "tokentrim_valid": v[1], "agree": v[2]} for k, v in cases.items()},
           "disagreements": disagreements}
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    main()
