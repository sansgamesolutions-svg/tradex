from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tradex.config.settings import settings


@dataclass(frozen=True)
class StockThresholds:
    min_bars: int = 1_250
    min_feature_samples: int = 1_000
    min_price: float = 5.0
    min_median_dollar_volume: float = 25_000_000.0
    dollar_volume_window: int = 252
    max_missing_session_rate: float = 0.01
    max_stale_sessions: int = 3
    min_minority_class_rate: float = 0.35
    walk_forward_folds: int = 4
    walk_forward_initial_fraction: float = 0.60
    min_median_roc_auc: float = 0.52
    min_median_balanced_accuracy: float = 0.51
    min_folds_beating_baseline: int = 3

    @classmethod
    def from_settings(cls) -> StockThresholds:
        return cls(
            min_bars=int(settings.stock_min_bars),
            min_feature_samples=int(settings.stock_min_feature_samples),
            min_price=float(settings.stock_min_price),
            min_median_dollar_volume=float(settings.stock_min_median_dollar_volume),
            dollar_volume_window=int(settings.stock_dollar_volume_window),
            max_missing_session_rate=float(settings.stock_max_missing_session_rate),
            max_stale_sessions=int(settings.stock_max_stale_sessions),
            min_minority_class_rate=float(settings.stock_min_minority_class_rate),
            walk_forward_folds=int(settings.stock_walk_forward_folds),
            walk_forward_initial_fraction=float(settings.stock_walk_forward_initial_fraction),
            min_median_roc_auc=float(settings.stock_min_median_roc_auc),
            min_median_balanced_accuracy=float(settings.stock_min_median_balanced_accuracy),
            min_folds_beating_baseline=int(settings.stock_min_folds_beating_baseline),
        )


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    bars: int
    feature_samples: int
    latest_close: float
    median_dollar_volume: float
    missing_session_rate: float
    stale_sessions: int
    minority_class_rate: float
    data_start: str
    data_end: str


@dataclass(frozen=True)
class FoldMetrics:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_samples: int
    test_samples: int
    roc_auc: float
    balanced_accuracy: float
    accuracy: float
    majority_baseline_accuracy: float
    beats_baseline: bool


@dataclass(frozen=True)
class StockQualification:
    symbol: str
    approved: bool
    eligibility: EligibilityResult | None = None
    folds: tuple[FoldMetrics, ...] = ()
    median_roc_auc: float | None = None
    median_balanced_accuracy: float | None = None
    folds_beating_baseline: int = 0
    rejection_reasons: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class QualificationReport:
    generated_at: str
    universe_name: str
    universe_retrieved_at: str
    universe_source_url: str
    model: str
    timeframe: str
    training_start: str
    thresholds: StockThresholds
    results: tuple[StockQualification, ...] = field(default_factory=tuple)

    @property
    def approved_symbols(self) -> tuple[str, ...]:
        return tuple(result.symbol for result in self.results if result.approved)

    def to_dict(self) -> dict:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "symbol",
            "approved",
            "data_eligible",
            "bars",
            "feature_samples",
            "latest_close",
            "median_dollar_volume",
            "missing_session_rate",
            "stale_sessions",
            "minority_class_rate",
            "median_roc_auc",
            "median_balanced_accuracy",
            "folds_beating_baseline",
            "rejection_reasons",
            "error",
        )
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for result in self.results:
                eligibility = result.eligibility
                writer.writerow(
                    {
                        "symbol": result.symbol,
                        "approved": result.approved,
                        "data_eligible": eligibility.eligible if eligibility else False,
                        "bars": eligibility.bars if eligibility else "",
                        "feature_samples": (eligibility.feature_samples if eligibility else ""),
                        "latest_close": eligibility.latest_close if eligibility else "",
                        "median_dollar_volume": (
                            eligibility.median_dollar_volume if eligibility else ""
                        ),
                        "missing_session_rate": (
                            eligibility.missing_session_rate if eligibility else ""
                        ),
                        "stale_sessions": (eligibility.stale_sessions if eligibility else ""),
                        "minority_class_rate": (
                            eligibility.minority_class_rate if eligibility else ""
                        ),
                        "median_roc_auc": result.median_roc_auc,
                        "median_balanced_accuracy": result.median_balanced_accuracy,
                        "folds_beating_baseline": result.folds_beating_baseline,
                        "rejection_reasons": "; ".join(result.rejection_reasons),
                        "error": result.error or "",
                    }
                )

    @classmethod
    def read_json(cls, path: Path) -> QualificationReport:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["thresholds"] = StockThresholds(**payload["thresholds"])
        payload["results"] = tuple(
            StockQualification(
                **{
                    **item,
                    "eligibility": (
                        EligibilityResult(
                            **{
                                **item["eligibility"],
                                "reasons": tuple(item["eligibility"]["reasons"]),
                            }
                        )
                        if item["eligibility"]
                        else None
                    ),
                    "folds": tuple(FoldMetrics(**fold) for fold in item["folds"]),
                    "rejection_reasons": tuple(item["rejection_reasons"]),
                }
            )
            for item in payload["results"]
        )
        return cls(**payload)
