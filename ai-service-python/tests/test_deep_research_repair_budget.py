import pytest
from services.deep_research.repair_budget import repair_prompt_byte_limit, REPAIR_OUTPUT_TOKENS
from services.deep_research.runtime import research_model_options


def test_observed_remaining_normal_pool_fits_without_raising_any_limit():
    budget = {'maxTokens': 100000, 'reserveTokens': 50000, 'tokens': 63217, 'normalTokens': 20707}
    assert repair_prompt_byte_limit(budget) == 20077
    assert budget['maxTokens'] == 100000


def test_total_pool_can_be_tighter_than_normal_pool():
    assert repair_prompt_byte_limit({'maxTokens': 100000, 'reserveTokens': 50000,
                                    'tokens': 90000, 'normalTokens': 100}) == 784


@pytest.mark.parametrize('used', [50000, 60000, True, -1, '100'])
def test_exhausted_or_invalid_capacity_never_creates_allowance(used):
    assert repair_prompt_byte_limit({'maxTokens': 100000, 'reserveTokens': 50000,
                                    'tokens': 1000, 'normalTokens': used}) == 0


def test_runtime_output_cap_matches_budget_planning():
    assert research_model_options('repair_claims', {})['max_tokens'] == REPAIR_OUTPUT_TOKENS
    assert repair_prompt_byte_limit({}) == 24000
    assert repair_prompt_byte_limit({'maxTokens': 100000}) == 24000


def test_exploration_leaves_room_for_whole_repair_request():
    from services.deep_research.contracts import check_exploration_headroom
    from services.deep_research.repair_budget import repair_exploration_headroom
    headroom = repair_exploration_headroom(50000)
    assert headroom == 33216
    budget = {'maxTokens': 100000, 'reserveTokens': 50000,
              'maxModelCalls': 18, 'reserveModelCalls': 5,
              'modelCalls': 5, 'normalTokens': 50000 - headroom}
    assert check_exploration_headroom(budget, 'extract') is None
    assert repair_prompt_byte_limit({**budget, 'tokens': budget['normalTokens']}) == 24000
    exhausted = {**budget, 'normalTokens': budget['normalTokens'] + 1}
    assert check_exploration_headroom(exhausted, 'extract')[0] == 'explorationTokens'
    assert check_exploration_headroom(exhausted, 'repair_claims') is None


def test_small_pool_keeps_exploration_and_final_pool_still_bounds_repair():
    from services.deep_research.repair_budget import repair_exploration_headroom
    assert repair_exploration_headroom(9000) == 6000
    # Protecting normal capacity never authorizes exceeding the overall pool.
    assert repair_prompt_byte_limit({'maxTokens': 100000, 'reserveTokens': 50000,
                                    'normalTokens': 10000, 'tokens': 99000}) == 0
