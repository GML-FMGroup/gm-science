"""Transparent compilation of natural-language analysis goals into supported operations."""

from __future__ import annotations

from typing import Any

from .config import AnalysisConfig

_CORRELATION_TERMS = ("correlation", "relationship", "association", "相关", "关系", "关联")
_GROUP_TERMS = ("group", "compare", "difference", "cohort", "分组", "比较", "差异", "组间")
_OUTLIER_TERMS = ("outlier", "anomaly", "extreme", "异常", "离群", "极值")
_DISTRIBUTION_TERMS = ("distribution", "histogram", "分布", "直方图")
_GENERIC_TERMS = ("analyze", "analysis", "explore", "overview", "summary", "分析", "探索", "概览", "总结")
_UNSUPPORTED_TERMS = {
    "causal": ("causal", "causality", "因果"),
    "regression": ("regression", "logistic", "回归"),
    "inferential_test": ("p-value", "significance", "t-test", "anova", "显著", "假设检验", "方差分析"),
    "survival": ("survival", "kaplan", "cox", "生存分析"),
}


def compile_analysis_plan(
    objective: str,
    datasets: list[dict[str, Any]],
    config: AnalysisConfig,
) -> dict[str, Any]:
    """Compile one objective into explicit operations over profiled datasets."""

    lowered = objective.casefold()
    dataset_plans: list[dict[str, Any]] = []
    all_numeric = False
    all_groupable = False
    for dataset in datasets:
        columns = list(dataset["profile"].get("columns") or [])
        numeric = [
            str(column["name"])
            for column in columns
            if column.get("inferred_type") in {"integer", "number"}
        ][: config.max_numeric_columns]
        categorical = [
            str(column["name"])
            for column in columns
            if column.get("inferred_type") in {"string", "boolean"}
            and 2 <= int(column.get("unique_count") or 0) <= config.max_group_categories
            and not column.get("unique_count_capped")
        ]
        all_numeric = all_numeric or bool(numeric)
        all_groupable = all_groupable or bool(numeric and categorical)
        dataset_plans.append(
            {
                "artifact_id": dataset["artifact_id"],
                "title": dataset["title"],
                "format": dataset["format"],
                "row_count": dataset["row_count"],
                "numeric_columns": numeric,
                "categorical_columns": categorical,
            }
        )

    requested_specific = any(
        _contains_any(lowered, terms)
        for terms in (_CORRELATION_TERMS, _GROUP_TERMS, _OUTLIER_TERMS, _DISTRIBUTION_TERMS)
    )
    generic = _contains_any(lowered, _GENERIC_TERMS) or not requested_specific
    operations = ["data_quality", "descriptive_statistics"]
    if all_numeric and (generic or _contains_any(lowered, _DISTRIBUTION_TERMS)):
        operations.append("distribution")
    if all_numeric and (generic or _contains_any(lowered, _OUTLIER_TERMS)):
        operations.append("iqr_outliers")
    if any(len(item["numeric_columns"]) >= 2 for item in dataset_plans) and (
        generic or _contains_any(lowered, _CORRELATION_TERMS)
    ):
        operations.append("pearson_correlation")
    if all_groupable and _contains_any(lowered, _GROUP_TERMS):
        operations.append("group_comparison")

    warnings: list[str] = []
    unsupported = [name for name, terms in _UNSUPPORTED_TERMS.items() if _contains_any(lowered, terms)]
    if unsupported:
        warnings.append(
            "Requested methods are outside the built-in deterministic analyst: "
            + ", ".join(unsupported)
            + ". The draft keeps descriptive operations only; add a reviewed custom Python Run for those methods."
        )
    if not all_numeric:
        warnings.append("No numeric columns were detected; numeric statistics and figures are omitted.")
    if _contains_any(lowered, _GROUP_TERMS) and not all_groupable:
        warnings.append("No bounded categorical-plus-numeric column pair is available for group comparison.")

    descriptions = {
        "data_quality": "Count rows, columns, missing values, and type coverage.",
        "descriptive_statistics": "Compute count, mean, median, standard deviation, minimum, quartiles, and maximum.",
        "distribution": "Render a deterministic SVG histogram for the first numeric column in each dataset.",
        "iqr_outliers": "Flag numeric values outside 1.5 times the interquartile range.",
        "pearson_correlation": "Compute pairwise Pearson correlations for complete numeric pairs.",
        "group_comparison": "Compare descriptive means across the first bounded categorical grouping column.",
    }
    assumptions = [
        "Missing values are excluded per calculation and reported explicitly.",
        "Numeric parsing follows the imported dataset profile and finite values only.",
        "Correlations describe linear association and do not establish causality.",
        "Group comparisons are descriptive; no significance claim is produced.",
        "IQR outliers are heuristic flags and are not automatically removed.",
    ]
    return {
        "version": 1,
        "objective": objective,
        "operations": operations,
        "steps": [
            {"id": operation, "title": operation.replace("_", " ").title(), "description": descriptions[operation]}
            for operation in operations
        ],
        "datasets": dataset_plans,
        "assumptions": assumptions,
        "warnings": warnings,
    }


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
