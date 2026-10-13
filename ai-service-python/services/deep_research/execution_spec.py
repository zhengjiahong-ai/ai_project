"""Structural validation for deep-research execution specs (stdlib only)."""

import math

EXECUTION_SPEC_CONTRACT = (
    "Add an executionSpec object to each groups, data and analysis claim. "
    "executionSpec schemas (all choices are proposed unexecuted settings; "
    "the application appends their explicit readable protocol before verification. "
    "Keep the short claim introduction consistent; never invent paper settings):\n"
    "The executionSpec object contains the fields directly: never wrap under data or analysis. "
    "The split field key is exactly offset, not zero-based offset. "
    "groups role: exactly {factors:nonempty list}. Each factor exactly {name:nonblank unique str, "
    "control:operation,treatment:operation}; operation exactly {action:nonblank str,parameters:list}; "
    "parameter exactly {name:nonblank unique str,type:number|choice,value:finite nonbool number "
    "for number or nonblank string for choice}. Include EVERY needed numeric threshold, level or "
    "rate as a number parameter with an actual proposed value, never a symbolic placeholder. "
    "choice is for categorical alternatives, never numeric thresholds disguised as strings. "
    "Empty parameters only for genuinely parameter-free actions. Describe how the factors "
    "combine into the experimental groups in the claim text.\n"
    "data role: dataset nonblank str; scenes {mode:named,names unique nonblank len>=1} "
    "or {mode:sorted_first,count positive int,order nonblank}; "
    "or {mode:all,count positive int} for ALL units of the exact cited dataset/subset. "
    "For all, ground the complete count and exact scope; do not invent ordering or require "
    "individual names when the cited complete benchmark is unambiguous. Never replace a "
    "subset with its parent dataset. "
    "split {mode:every_nth,order nonblank,stride int>=2,offset int 0<=offset<stride (zero-based)} "
    "or {mode:explicit,train/evaluation nonempty unique disjoint str lists} "
    "or {mode:seeded_fraction,evaluationFraction finite 0<f<1,seed nonneg int}; "
    "seeds nonempty unique nonneg ints; independentUnit nonblank str; "
    "replication {mode:fixed_checkpoint|retrained_per_seed}.\n"
    "analysis role: effects nonempty dict name->nonblank formula; "
    "uncertainty {mode:descriptive,boundary nonblank;decision.mode=descriptive} "
    "or {mode:paired_cluster_bootstrap,unit nonblank,repetitions int>=100,"
    "confidence 0<c<1,seed nonneg int} "
    "or {mode:analytic,method nonblank,assumptions nonblank list,confidence 0<c<1}; "
    "decision {mode:descriptive,boundary nonblank} "
    "or {mode:interval_excludes_zero} "
    "or {mode:equivalence,tolerances nonempty dict metric->finite positive}.\n"
    "One claim per role; complete spec for own role; semantic reviewer checks "
    "consistency, correctness, unit independence, concrete meaning separately. "
    "Seeds, splits and intervention levels can be proposed; the existence and capacity "
    "of a named existing dataset/subset cannot. For data selection, cite fulltext "
    "evidence establishing enough units in that EXACT subset, or the actual selected "
    "unit names. An inherited subset in another paper requires checking that paper; "
    "the parent dataset's capacity does not establish the subset's capacity. "
    "Do not invent availability, substitute a different subset, or claim a conditional "
    "unverified data choice is already executable. State unresolved availability plainly."
)


def _is_nonblank_str(v):
    return isinstance(v, str) and v.strip() != ""


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_finite_num(v):
    return _is_int(v) or (isinstance(v, float) and math.isfinite(v))


def _all_unique(seq):
    try:
        return len(set(seq)) == len(seq)
    except TypeError:
        return False


def _check_str_list(lst, path, add):
    if not isinstance(lst, list) or len(lst) == 0:
        add(path)
        return
    for i, item in enumerate(lst):
        if not _is_nonblank_str(item):
            add(f"{path}[{i}]")
    if not _all_unique(lst):
        add(path)


def _validate_scenes(scenes, add):
    mode = scenes.get("mode")
    if mode == 'all':
        if not _is_int(scenes.get('count')) or scenes['count'] <= 0:
            add('scenes.count')
        if set(scenes) != {'mode', 'count'}:
            add('scenes.all_conflicting_selection')
    elif mode == "named":
        names = scenes.get("names")
        if not isinstance(names, list) or len(names) == 0:
            add("scenes.names")
        else:
            for i, n in enumerate(names):
                if not _is_nonblank_str(n):
                    add(f"scenes.names[{i}]")
            if not _all_unique(names):
                add("scenes.names")
    elif mode == "sorted_first":
        count = scenes.get("count")
        if not _is_int(count) or count <= 0:
            add("scenes.count")
        if not _is_nonblank_str(scenes.get("order")):
            add("scenes.order")
    else:
        add("scenes.mode")


def _validate_split(split, add):
    mode = split.get("mode")
    if mode == "every_nth":
        if not _is_nonblank_str(split.get("order")):
            add("split.order")
        stride = split.get("stride")
        if not _is_int(stride) or stride < 2:
            add("split.stride")
        offset = split.get("offset")
        if not _is_int(offset) or offset < 0:
            add("split.offset")
        elif _is_int(stride) and stride >= 2 and offset >= stride:
            add("split.offset")
    elif mode == "explicit":
        train = split.get("train")
        evaluation = split.get("evaluation")
        _check_str_list(train, "split.train", add)
        _check_str_list(evaluation, "split.evaluation", add)
        if isinstance(train, list) and isinstance(evaluation, list):
            try:
                if set(train) & set(evaluation):
                    add("split.train")
                    add("split.evaluation")
            except TypeError:
                pass
    elif mode == "seeded_fraction":
        ef = split.get("evaluationFraction")
        if not _is_finite_num(ef) or not (0 < ef < 1):
            add("split.evaluationFraction")
        seed = split.get("seed")
        if not _is_int(seed) or seed < 0:
            add("split.seed")
    else:
        add("split.mode")


def _validate_data(spec, add):
    if not _is_nonblank_str(spec.get("dataset")):
        add("dataset")
    scenes = spec.get("scenes")
    if not isinstance(scenes, dict):
        add("scenes")
    else:
        _validate_scenes(scenes, add)
    split = spec.get("split")
    if not isinstance(split, dict):
        add("split")
    else:
        _validate_split(split, add)
    seeds = spec.get("seeds")
    if not isinstance(seeds, list) or len(seeds) == 0:
        add("seeds")
    else:
        for i, s in enumerate(seeds):
            if not _is_int(s) or s < 0:
                add(f"seeds[{i}]")
        if not _all_unique(seeds):
            add("seeds")
    if not _is_nonblank_str(spec.get("independentUnit")):
        add("independentUnit")
    replication = spec.get("replication")
    if not isinstance(replication, dict):
        add("replication")
    elif replication.get("mode") not in ("fixed_checkpoint", "retrained_per_seed"):
        add("replication.mode")


def _validate_uncertainty(uncertainty, spec, add):
    mode = uncertainty.get("mode")
    if mode == "descriptive":
        if not _is_nonblank_str(uncertainty.get("boundary")):
            add("uncertainty.boundary")
        decision = spec.get("decision")
        if isinstance(decision, dict) and decision.get("mode") != "descriptive":
            add("decision.mode")
    elif mode == "paired_cluster_bootstrap":
        if not _is_nonblank_str(uncertainty.get("unit")):
            add("uncertainty.unit")
        reps = uncertainty.get("repetitions")
        if not _is_int(reps) or reps < 100:
            add("uncertainty.repetitions")
        conf = uncertainty.get("confidence")
        if not _is_finite_num(conf) or not (0 < conf < 1):
            add("uncertainty.confidence")
        seed = uncertainty.get("seed")
        if not _is_int(seed) or seed < 0:
            add("uncertainty.seed")
    elif mode == "analytic":
        if not _is_nonblank_str(uncertainty.get("method")):
            add("uncertainty.method")
        assumptions = uncertainty.get("assumptions")
        if not isinstance(assumptions, list) or len(assumptions) == 0:
            add("uncertainty.assumptions")
        else:
            for i, a in enumerate(assumptions):
                if not _is_nonblank_str(a):
                    add(f"uncertainty.assumptions[{i}]")
        conf = uncertainty.get("confidence")
        if not _is_finite_num(conf) or not (0 < conf < 1):
            add("uncertainty.confidence")
    else:
        add("uncertainty.mode")


def _validate_decision(decision, add):
    mode = decision.get("mode")
    if mode == "descriptive":
        if not _is_nonblank_str(decision.get("boundary")):
            add("decision.boundary")
    elif mode == "interval_excludes_zero":
        pass
    elif mode == "equivalence":
        tolerances = decision.get("tolerances")
        if not isinstance(tolerances, dict) or len(tolerances) == 0:
            add("decision.tolerances")
        else:
            for metric, tol in tolerances.items():
                if not isinstance(metric, str) or not metric.strip():
                    add("decision.tolerances")
                elif not _is_finite_num(tol) or tol <= 0:
                    add(f"decision.tolerances.{metric}")
    else:
        add("decision.mode")


def _validate_analysis(spec, add):
    effects = spec.get("effects")
    if not isinstance(effects, dict) or len(effects) == 0:
        add("effects")
    else:
        for name, formula in effects.items():
            if not isinstance(name, str) or not name.strip():
                add("effects")
            elif not _is_nonblank_str(formula):
                add(f"effects.{name}")
    uncertainty = spec.get("uncertainty")
    if not isinstance(uncertainty, dict):
        add("uncertainty")
    else:
        _validate_uncertainty(uncertainty, spec, add)
    decision = spec.get("decision")
    if not isinstance(decision, dict):
        add("decision")
    else:
        _validate_decision(decision, add)


def execution_spec_errors(role, spec):
    """Return stable unique field-path errors. Never raises; never mutates."""
    if role == 'groups':
        from services.deep_research.group_spec import validate_group_spec
        return validate_group_spec(spec)
    if role not in ("data", "analysis"):
        return []
    errors = []
    seen = set()

    def add(path):
        if path not in seen:
            seen.add(path)
            errors.append(path)

    if not isinstance(spec, dict):
        add("spec")
        return errors
    if 'data' in spec or 'analysis' in spec:
        add('ambiguous_role_wrapper')
    if isinstance(spec.get('split'), dict) and 'zero-based offset' in spec['split']:
        add('split.ambiguous_offset')
    if role == "data":
        _validate_data(spec, add)
    else:
        _validate_analysis(spec, add)
    return errors
