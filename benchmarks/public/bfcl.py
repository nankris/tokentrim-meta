"""BFCL v3 (Berkeley Function Calling Leaderboard; Apache-2.0; HF gorilla-llm/Berkeley-Function-Calling-Leaderboard)
loader, OpenAI-tool conversion and AST checker.

The checker is a faithful REIMPLEMENTATION (written for TokenTrim, not copied) of the Python-language rules in
bfcl_eval/eval_checker/ast_eval/ast_checker.py at gorilla commit 6ea5797 (2026-03-23):
* ``multiple`` categories: exactly one call, checked against the single ground-truth function;
* ``parallel`` categories: same number of calls, matched to ground truth in any order;
* per call: name must match (dots replaced by underscores, as BFCL does for OpenAI-style models), every required
  parameter present, no parameter outside the schema / possible answer, type check (int accepted for float),
  values must be one of the possible answers; strings compared after BFCL's standardisation (drop spaces and
  ``,./-_*^``, lowercase, ' -> "); lists element-wise standardised; dicts and lists of dicts checked key by key;
  a possible-answer parameter absent from the call is allowed only if ``""`` is among its possible values.
Verified by benchmarks/public/bfcl_diffcheck.py against the official checker (results/public_slices/). Data is not vendored; ``BFCL_DIR`` points at the download (DATA_SOURCES.md).
"""
import copy
import json
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("BFCL_DIR", "/workspace/pubdata/bfcl"))
PY = {"string": str, "integer": int, "float": float, "boolean": bool, "array": list, "tuple": list, "dict": dict,
      "any": str}
TO_OPENAI = {"integer": "integer", "number": "number", "float": "number", "string": "string", "boolean": "boolean",
             "bool": "boolean", "array": "array", "list": "array", "dict": "object", "object": "object",
             "tuple": "array", "any": "string"}


def load(category: str):
    q = [json.loads(l) for l in open(ROOT / f"BFCL_v3_{category}.json", encoding="utf-8")]
    # joined on the index before the first "-": upstream has one id typo (question live_multiple_1052-79-0 vs
    # answer live_multiple_1052-279-0)
    a = {json.loads(l)["id"].split("-")[0]: json.loads(l)["ground_truth"]
         for l in open(ROOT / "possible_answer" / f"BFCL_v3_{category}.json", encoding="utf-8")}
    for item in q:
        item["ground_truth"] = a[item["id"].split("-")[0]]
        item["category"] = category
    return q


def oai_name(name: str) -> str:
    return re.sub(r"\.", "_", name)


def _cast(props: dict) -> dict:
    for key, v in props.items():
        t = v.get("type")
        if t is None:
            v["type"] = "string"
        else:
            if t == "float":
                v["format"] = "float"
                v["description"] = v.get("description", "") + " This is a float type value."
            v["type"] = TO_OPENAI.get(t, "string")
        if v["type"] in ("array", "object"):
            if "properties" in v:
                v["properties"] = _cast(v["properties"])
            elif "items" in v and isinstance(v["items"], dict) and "type" in v["items"]:
                v["items"]["type"] = TO_OPENAI.get(v["items"]["type"], "string")
                if v["items"]["type"] == "object" and "properties" in v["items"]:
                    v["items"]["properties"] = _cast(v["items"]["properties"])
                elif v["items"]["type"] == "array" and isinstance(v["items"].get("items"), dict) \
                        and "type" in v["items"]["items"]:
                    v["items"]["items"]["type"] = TO_OPENAI.get(v["items"]["items"]["type"], "string")
    return props


def to_tools(functions: list[dict]) -> list[dict]:
    """BFCL function docs -> OpenAI tools, as BFCL's OpenAI FC handler does (Python-syntax note, type mapping)."""
    tools = []
    for f in copy.deepcopy(functions):
        f["name"] = oai_name(f["name"])
        f["description"] = f.get("description", "") + " Note that the provided function is in Python 3 syntax."
        params = f.get("parameters") or {"properties": {}}
        params["type"] = "object"
        params["properties"] = _cast(params.get("properties") or {})
        f["parameters"] = params
        tools.append({"type": "function", "function": f})
    return tools


def decode(tool_calls) -> list[dict] | None:
    out = []
    for c in tool_calls or []:
        fn = c.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            return None
        if not isinstance(args, dict):
            return None
        out.append({fn.get("name", ""): args})
    return out


# ---- checker ---------------------------------------------------------------------------------------------
def std(s: str) -> str:
    return re.sub(r"[ \,\.\/\-\_\*\^]", "", s).lower().replace("'", '"')


def _std_list(xs):
    return [std(x) if isinstance(x, str) else x for x in xs]


def _dict_ok(value: dict, options: list) -> bool:
    for opt in options:
        if opt == "" or not isinstance(opt, dict):
            continue
        ok = True
        for k, v in value.items():
            if k not in opt or (std(v) if isinstance(v, str) else v) not in _std_list(opt[k]):
                ok = False
                break
        if ok and all(k in value or "" in v for k, v in opt.items()):
            return True
    return False


def _list_dict_ok(value: list, options: list) -> bool:
    for opt in options:
        if isinstance(opt, list) and len(opt) == len(value) and all(
                isinstance(d, dict) and _dict_ok(d, [o]) for d, o in zip(value, opt)):
            return True
    return False


def _answer_type(options):
    for o in options:
        if o != "":
            return type(o)
    return None


def check_call(desc: dict, call: dict, truth: dict) -> tuple[bool, str]:
    """One call vs one ground-truth entry {name: {param: [options]}}."""
    expected = oai_name(next(iter(truth)))
    options = next(iter(truth.values()))
    if expected not in call:
        return False, "wrong_func_name"
    args = call[expected]
    props = (desc.get("parameters") or {}).get("properties") or {}
    for p in (desc.get("parameters") or {}).get("required") or []:
        if p not in args:
            return False, "missing_required"
    for p, value in args.items():
        if p not in props or p not in options:
            return False, "unexpected_param"
        tdesc = props[p].get("type", "string")
        tconv = PY.get(tdesc, str)
        nested = None
        if tdesc in ("array", "tuple"):
            nested = PY.get(((props[p].get("items") or {}).get("type")), None)
        if tdesc == "float" and type(value) is int:
            value = float(value)
        pa_type = _answer_type(options[p])
        variable = pa_type is not None and pa_type != tconv
        if type(value) is not tconv:
            if pa_type is not None and type(value) is pa_type:
                variable = True
            else:
                return False, "type_error"
        elif nested is not None and not variable:
            ok = False
            for opt in options[p]:
                if isinstance(opt, list) and all(type(x) is nested or (nested is float and type(x) is int)
                                                 for x in value):
                    ok = True
                    break
            if not ok:  # as in BFCL: a failed nested check still passes as a "variable" if the type matches
                if pa_type is not None and type(value) is pa_type:
                    variable = True
                else:
                    return False, "type_error:nested"
        if not variable:
            if tconv is dict:
                if not _dict_ok(value, options[p]):
                    return False, "value_error:dict"
                continue
            if tconv is list and nested is dict:
                if not _list_dict_ok(value, options[p]):
                    return False, "value_error:list_dict"
                continue
            if tconv is str:
                if std(value) not in [std(o) for o in options[p] if isinstance(o, str)]:
                    return False, "value_error:string"
                continue
            if tconv is list:
                if _std_list(value) not in [_std_list(o) for o in options[p] if isinstance(o, list)]:
                    return False, "value_error:list"
                continue
        if value not in options[p]:
            return False, "value_error:other"
    for p, opts in options.items():
        if p not in args and "" not in opts:
            return False, "missing_optional"
    return True, ""


def check(item: dict, output: list[dict] | None) -> tuple[bool, str]:
    """AST check for the ``multiple`` / ``parallel`` categories."""
    if output is None:
        return False, "undecodable"
    truth = item["ground_truth"]
    if len(output) != len(truth):
        return False, "wrong_count" if output else "no_call"
    descs = {oai_name(f["name"]): f for f in item["function"]}
    if "parallel" not in item["category"]:
        return check_call(descs.get(oai_name(next(iter(truth[0]))), {}), output[0], truth[0])
    used = set()
    for t in truth:
        d = descs.get(oai_name(next(iter(t))), {})
        hit = next((i for i, o in enumerate(output) if i not in used and check_call(d, o, t)[0]), None)
        if hit is None:
            return False, "parallel_no_match"
        used.add(hit)
    return True, ""


def oracle_output(item: dict) -> list[dict]:
    """A call built from the first non-empty option of every ground-truth parameter (grader self-test)."""
    def first(opts):  # first non-empty option, materialising nested {key: [options]} dicts
        for o in opts:
            if o != "":
                return value(o)
        return None

    def value(o):
        if isinstance(o, dict):
            return {k: first(v) for k, v in o.items() if isinstance(v, list) and first(v) is not None}
        if isinstance(o, list) and o and all(isinstance(d, dict) for d in o):
            return [value(d) for d in o]
        return o

    out = []
    for t in item["ground_truth"]:
        name, opts = next(iter(t.items()))
        out.append({oai_name(name): {p: first(o) for p, o in opts.items() if first(o) is not None}})
    return out
