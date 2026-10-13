"""Tests for execution_spec structural validation."""

import copy
import unittest

from services.deep_research.execution_spec import (
    EXECUTION_SPEC_CONTRACT,
    execution_spec_errors,
)


def valid_data_spec():
    return {
        "dataset": "experiment_results",
        "scenes": {"mode": "named", "names": ["scene_a", "scene_b"]},
        "split": {"mode": "explicit", "train": ["s1", "s2"], "evaluation": ["s3", "s4"]},
        "seeds": [0, 1, 42],
        "independentUnit": "participant",
        "replication": {"mode": "fixed_checkpoint"},
    }


def valid_analysis_spec():
    return {
        "effects": {"main": "y ~ condition"},
        "uncertainty": {
            "mode": "paired_cluster_bootstrap",
            "unit": "participant",
            "repetitions": 1000,
            "confidence": 0.95,
            "seed": 7,
        },
        "decision": {"mode": "interval_excludes_zero"},
    }


class TestValidSpecs(unittest.TestCase):
    def test_valid_data(self):
        self.assertEqual(execution_spec_errors("data", valid_data_spec()), [])

    def test_valid_analysis(self):
        self.assertEqual(execution_spec_errors("analysis", valid_analysis_spec()), [])

    def test_data_sorted_first(self):
        spec = valid_data_spec()
        spec["scenes"] = {"mode": "sorted_first", "count": 5, "order": "by score desc"}
        self.assertEqual(execution_spec_errors("data", spec), [])

    def test_data_every_nth(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "every_nth", "order": "row order", "stride": 3, "offset": 1}
        self.assertEqual(execution_spec_errors("data", spec), [])

    def test_data_seeded_fraction(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "seeded_fraction", "evaluationFraction": 0.2, "seed": 0}
        self.assertEqual(execution_spec_errors("data", spec), [])

    def test_analysis_descriptive(self):
        spec = {
            "effects": {"main": "y ~ x"},
            "uncertainty": {"mode": "descriptive", "boundary": "+/- 0.5"},
            "decision": {"mode": "descriptive", "boundary": "0.5"},
        }
        self.assertEqual(execution_spec_errors("analysis", spec), [])

    def test_analysis_analytic(self):
        spec = {
            "effects": {"main": "y ~ x"},
            "uncertainty": {
                "mode": "analytic",
                "method": "Welch t",
                "assumptions": ["normality"],
                "confidence": 0.95,
            },
            "decision": {"mode": "interval_excludes_zero"},
        }
        self.assertEqual(execution_spec_errors("analysis", spec), [])

    def test_analysis_equivalence(self):
        spec = valid_analysis_spec()
        spec["decision"] = {"mode": "equivalence", "tolerances": {"accuracy": 0.05}}
        self.assertEqual(execution_spec_errors("analysis", spec), [])


class TestMalformedTypes(unittest.TestCase):
    def test_spec_none(self):
        self.assertEqual(execution_spec_errors("data", None), ["spec"])

    def test_spec_list(self):
        self.assertEqual(execution_spec_errors("data", [1, 2]), ["spec"])

    def test_spec_bool(self):
        self.assertEqual(execution_spec_errors("analysis", True), ["spec"])

    def test_dataset_not_string(self):
        spec = valid_data_spec()
        spec["dataset"] = 123
        self.assertIn("dataset", execution_spec_errors("data", spec))

    def test_dataset_blank(self):
        spec = valid_data_spec()
        spec["dataset"] = "   "
        self.assertIn("dataset", execution_spec_errors("data", spec))

    def test_scenes_not_dict(self):
        spec = valid_data_spec()
        spec["scenes"] = "named"
        self.assertIn("scenes", execution_spec_errors("data", spec))

    def test_seeds_bool_rejected(self):
        spec = valid_data_spec()
        spec["seeds"] = [True, 1]
        self.assertIn("seeds[0]", execution_spec_errors("data", spec))

    def test_seeds_negative(self):
        spec = valid_data_spec()
        spec["seeds"] = [-1]
        self.assertIn("seeds[0]", execution_spec_errors("data", spec))

    def test_seeds_duplicate(self):
        spec = valid_data_spec()
        spec["seeds"] = [1, 1]
        self.assertIn("seeds", execution_spec_errors("data", spec))

    def test_seeds_empty(self):
        spec = valid_data_spec()
        spec["seeds"] = []
        self.assertIn("seeds", execution_spec_errors("data", spec))

    def test_replication_bad_mode(self):
        spec = valid_data_spec()
        spec["replication"] = {"mode": "unknown"}
        self.assertIn("replication.mode", execution_spec_errors("data", spec))

    def test_effects_empty(self):
        spec = valid_analysis_spec()
        spec["effects"] = {}
        self.assertIn("effects", execution_spec_errors("analysis", spec))

    def test_effects_not_dict(self):
        spec = valid_analysis_spec()
        spec["effects"] = ["y ~ x"]
        self.assertIn("effects", execution_spec_errors("analysis", spec))

    def test_effects_blank_formula(self):
        spec = valid_analysis_spec()
        spec["effects"] = {"main": ""}
        self.assertIn("effects.main", execution_spec_errors("analysis", spec))


class TestNaNInfinite(unittest.TestCase):
    def test_nan_confidence(self):
        spec = valid_analysis_spec()
        spec["uncertainty"]["confidence"] = float("nan")
        self.assertIn("uncertainty.confidence", execution_spec_errors("analysis", spec))

    def test_inf_confidence(self):
        spec = valid_analysis_spec()
        spec["uncertainty"]["confidence"] = float("inf")
        self.assertIn("uncertainty.confidence", execution_spec_errors("analysis", spec))

    def test_nan_fraction(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "seeded_fraction", "evaluationFraction": float("nan"), "seed": 0}
        self.assertIn("split.evaluationFraction", execution_spec_errors("data", spec))

    def test_inf_tolerance(self):
        spec = valid_analysis_spec()
        spec["decision"] = {"mode": "equivalence", "tolerances": {"m": float("inf")}}
        self.assertIn("decision.tolerances.m", execution_spec_errors("analysis", spec))


class TestExplicitSplitDisjoint(unittest.TestCase):
    def test_overlap_flagged(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "explicit", "train": ["s1", "s2"], "evaluation": ["s2", "s3"]}
        errs = execution_spec_errors("data", spec)
        self.assertIn("split.train", errs)
        self.assertIn("split.evaluation", errs)

    def test_disjoint_ok(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "explicit", "train": ["a"], "evaluation": ["b"]}
        errs = execution_spec_errors("data", spec)
        self.assertNotIn("split.train", errs)
        self.assertNotIn("split.evaluation", errs)


class TestDeterministicSelection(unittest.TestCase):
    def test_count_bool_rejected(self):
        spec = valid_data_spec()
        spec["scenes"] = {"mode": "sorted_first", "count": True, "order": "by x"}
        self.assertIn("scenes.count", execution_spec_errors("data", spec))

    def test_missing_order(self):
        spec = valid_data_spec()
        spec["scenes"] = {"mode": "sorted_first", "count": 3}
        self.assertIn("scenes.order", execution_spec_errors("data", spec))

    def test_offset_gte_stride(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "every_nth", "order": "row", "stride": 3, "offset": 3}
        self.assertIn("split.offset", execution_spec_errors("data", spec))

    def test_stride_one(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "every_nth", "order": "row", "stride": 1, "offset": 0}
        self.assertIn("split.stride", execution_spec_errors("data", spec))


class TestUnknownModes(unittest.TestCase):
    def test_scenes_unknown(self):
        spec = valid_data_spec()
        spec["scenes"] = {"mode": "random"}
        self.assertIn("scenes.mode", execution_spec_errors("data", spec))

    def test_split_unknown(self):
        spec = valid_data_spec()
        spec["split"] = {"mode": "kfold"}
        self.assertIn("split.mode", execution_spec_errors("data", spec))

    def test_uncertainty_unknown(self):
        spec = valid_analysis_spec()
        spec["uncertainty"] = {"mode": "bayesian"}
        self.assertIn("uncertainty.mode", execution_spec_errors("analysis", spec))

    def test_decision_unknown(self):
        spec = valid_analysis_spec()
        spec["decision"] = {"mode": "pvalue"}
        self.assertIn("decision.mode", execution_spec_errors("analysis", spec))


class TestUnsupportedRoles(unittest.TestCase):
    def test_unknown_role(self):
        self.assertEqual(execution_spec_errors("writing", {"x": 1}), [])

    def test_none_role(self):
        self.assertEqual(execution_spec_errors(None, {}), [])

    def test_empty_role(self):
        self.assertEqual(execution_spec_errors("", {"x": 1}), [])


class TestPreservation(unittest.TestCase):
    def test_no_mutation_data(self):
        spec = valid_data_spec()
        original = copy.deepcopy(spec)
        execution_spec_errors("data", spec)
        self.assertEqual(spec, original)

    def test_no_mutation_analysis(self):
        spec = valid_analysis_spec()
        original = copy.deepcopy(spec)
        execution_spec_errors("analysis", spec)
        self.assertEqual(spec, original)

    def test_no_mutation_malformed(self):
        spec = {"dataset": ["nested", {"x": 1}], "seeds": [[1, 2]]}
        original = copy.deepcopy(spec)
        execution_spec_errors("data", spec)
        self.assertEqual(spec, original)


class TestDescriptiveCrossCheck(unittest.TestCase):
    def test_descriptive_requires_matching_decision(self):
        spec = {
            "effects": {"main": "y ~ x"},
            "uncertainty": {"mode": "descriptive", "boundary": "0.5"},
            "decision": {"mode": "interval_excludes_zero"},
        }
        self.assertIn("decision.mode", execution_spec_errors("analysis", spec))


class TestUnhashable(unittest.TestCase):
    def test_seeds_list_item(self):
        spec = valid_data_spec()
        spec["seeds"] = [[1, 2], 3]
        self.assertIn("seeds[0]", execution_spec_errors("data", spec))

    def test_names_dict_item(self):
        spec = valid_data_spec()
        spec["scenes"] = {"mode": "named", "names": [{"a": 1}]}
        self.assertIn("scenes.names[0]", execution_spec_errors("data", spec))


class TestContract(unittest.TestCase):
    def test_is_nontrivial_string(self):
        self.assertIsInstance(EXECUTION_SPEC_CONTRACT, str)
        self.assertGreater(len(EXECUTION_SPEC_CONTRACT), 100)

    def test_mentions_both_roles(self):
        self.assertIn("data", EXECUTION_SPEC_CONTRACT)
        self.assertIn("analysis", EXECUTION_SPEC_CONTRACT)


if __name__ == "__main__":
    unittest.main()
