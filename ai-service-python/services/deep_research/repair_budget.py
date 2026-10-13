"""Request fitting is advisory; the ledger still reserves atomically."""
REPAIR_OUTPUT_TOKENS = 8192
FRAMING_TOKENS = 1024
REPAIR_INPUT_BYTES = 24000


def repair_exploration_headroom(normal_pool):
    """Protect one full repair request while retaining exploration capacity.

    Small custom pools keep at least one third for exploration; the repair
    fitter still refuses requests that cannot fit the remaining actual budget.
    """
    return min(REPAIR_INPUT_BYTES + REPAIR_OUTPUT_TOKENS + FRAMING_TOKENS,
               max(0, normal_pool) * 2 // 3)


def repair_prompt_byte_limit(budget):
    if not budget or 'maxTokens' not in budget:
        return REPAIR_INPUT_BYTES
    keys = ('maxTokens', 'reserveTokens', 'tokens', 'normalTokens')
    values = [budget.get(key, 0) for key in keys]
    if any(type(value) is not int or value < 0 for value in values):
        return 0
    maximum, reserve, total_used, normal_used = values
    remaining = min(maximum - total_used, maximum - reserve - normal_used)
    return max(0, min(REPAIR_INPUT_BYTES, remaining - REPAIR_OUTPUT_TOKENS - FRAMING_TOKENS))
