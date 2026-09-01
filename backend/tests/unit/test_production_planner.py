import pytest

from app.domains.production.planner import split_production_batches


def sizes(result):
    return [(item.serving_count,item.official,item.source_serving_count) for item in result]


def test_exact_official_version_is_used():
    assert sizes(split_production_batches(500,100,[(100,"v100"),(50,"v50")]))==[(100,True,100)]*5


def test_exact_official_combination_beats_larger_greedy_first_choice():
    result=split_production_batches(120,100,[(100,"v100"),(60,"v60")])
    assert sizes(result)==[(60,True,60),(60,True,60)]


def test_exact_mixed_official_combination_has_no_estimate():
    result=split_production_batches(280,100,[(100,"v100"),(50,"v50"),(30,"v30")])
    assert sizes(result)==[(100,True,100),(100,True,100),(50,True,50),(30,True,30)]


def test_deterministic_optimal_split_and_smallest_estimated_remainder():
    versions=[(100,"v100"),(50,"v50"),(30,"v30")]
    expected=[(100,True,100),(100,True,100),(50,True,50),(30,True,30),(6,False,30)]
    assert sizes(split_production_batches(286,100,versions))==expected
    assert sizes(split_production_batches(286,100,list(reversed(versions))))==expected


def test_large_plan_uses_largest_formal_versions_first():
    assert sizes(split_production_batches(730,200,[(50,"v50"),(100,"v100"),(150,"v150"),(200,"v200")]))==[
        (200,True,200),(200,True,200),(200,True,200),(100,True,100),(30,False,50)
    ]


def test_five_hundred_is_all_official_with_minimum_batches_and_larger_version_tie_break():
    result=split_production_batches(500,200,[(200,"v200"),(150,"v150"),(100,"v100"),(50,"v50")])
    assert sizes(result)==[(200,True,200),(200,True,200),(100,True,100)]


def test_no_official_version_uses_bounded_estimated_batches():
    assert sizes(split_production_batches(450,200,[]))==[(200,False,None),(200,False,None),(50,False,None)]


@pytest.mark.parametrize(("total","maximum"),[(0,100),(100,0),(-1,100)])
def test_invalid_serving_values_are_rejected(total,maximum):
    with pytest.raises(ValueError):split_production_batches(total,maximum,[])
