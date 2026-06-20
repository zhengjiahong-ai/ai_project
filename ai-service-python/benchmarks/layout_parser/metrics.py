from __future__ import annotations

import re
from itertools import combinations
from typing import Any


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def bbox_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_x1 = float(left.get("left", 0))
    left_y1 = float(left.get("top", 0))
    left_x2 = left_x1 + max(float(left.get("width", 0)), 0)
    left_y2 = left_y1 + max(float(left.get("height", 0)), 0)
    right_x1 = float(right.get("left", 0))
    right_y1 = float(right.get("top", 0))
    right_x2 = right_x1 + max(float(right.get("width", 0)), 0)
    right_y2 = right_y1 + max(float(right.get("height", 0)), 0)

    intersection_width = max(min(left_x2, right_x2) - max(left_x1, right_x1), 0)
    intersection_height = max(min(left_y2, right_y2) - max(left_y1, right_y1), 0)
    intersection = intersection_width * intersection_height
    union = max((left_x2 - left_x1) * (left_y2 - left_y1), 0) + max(
        (right_x2 - right_x1) * (right_y2 - right_y1), 0
    ) - intersection
    return intersection / union if union else 0.0


def _normalize_heading(value: Any) -> str:
    text = " ".join(str(value or "").lower().split())
    text = re.sub(
        r"^(?:[a-z]?\d+(?:[.\-]\d+)*|[ivxlcdm]+)(?:[.)]|\s)+",
        "",
        text,
    )
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text).strip()


def score_headings(predicted: list[str], gold: list[str]) -> dict[str, Any]:
    remaining = [_normalize_heading(item) for item in gold]
    matched = 0
    for candidate in (_normalize_heading(item) for item in predicted):
        if candidate and candidate in remaining:
            remaining.remove(candidate)
            matched += 1
    precision = _safe_ratio(matched, len(predicted))
    recall = _safe_ratio(matched, len(gold))
    return {
        "predicted": len(predicted),
        "gold": len(gold),
        "matched": matched,
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }


def score_reading_order(predicted: list[str], gold: list[str]) -> dict[str, Any]:
    predicted_positions = {anchor: index for index, anchor in enumerate(predicted)}
    shared = [anchor for anchor in gold if anchor in predicted_positions]
    correct_pairs = sum(
        1
        for left, right in combinations(shared, 2)
        if predicted_positions[left] < predicted_positions[right]
    )
    comparable_pairs = len(shared) * (len(shared) - 1) // 2
    return {
        "goldAnchors": len(gold),
        "matchedAnchors": len(shared),
        "comparablePairs": comparable_pairs,
        "correctPairs": correct_pairs,
        "accuracy": _safe_ratio(correct_pairs, comparable_pairs),
    }


def score_regions(
    predicted: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    unmatched_gold = set(range(len(gold)))
    matched = 0
    for candidate in predicted:
        best_index = None
        best_iou = 0.0
        for index in unmatched_gold:
            expected = gold[index]
            if candidate.get("pageIndex") != expected.get("pageIndex") or candidate.get("type") != expected.get("type"):
                continue
            current_iou = bbox_iou(candidate.get("bbox") or {}, expected.get("bbox") or {})
            if current_iou >= iou_threshold and current_iou > best_iou:
                best_index = index
                best_iou = current_iou
        if best_index is not None:
            unmatched_gold.remove(best_index)
            matched += 1

    precision = _safe_ratio(matched, len(predicted))
    recall = _safe_ratio(matched, len(gold))
    return {
        "predicted": len(predicted),
        "gold": len(gold),
        "matched": matched,
        "falsePositives": len(predicted) - matched,
        "falseNegatives": len(gold) - matched,
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "iouThreshold": iou_threshold,
    }
