from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tradex.config.settings import settings
from tradex.stocks.types import FoldMetrics


@dataclass(frozen=True)
class CryptoThresholds:
    min_bars: int = 700
    min_feature_samples: int = 500
    min_median_quote_volume: float = 1_000_000.0
    quote_volume_window: int = 90
    max_missing_day_rate: float = 0.01
    max_stale_days: int = 2
    min_minority_class_rate: float = 0.35
    walk_forward_folds: int = 4
    walk_forward_initial_fraction: float = 0.60
    min_median_roc_auc: float = 0.52
    min_median_balanced_accuracy: float = 0.51
    min_folds_beating_baseline: int = 3

    @classmethod
    def from_settings(cls) -> CryptoThresholds:
        return cls(
            min_bars=int(settings.crypto_min_bars),
            min_feature_samples=int(settings.crypto_min_feature_samples),
            min_median_quote_volume=float(settings.crypto_min_median_quote_volume),
            quote_volume_window=int(settings.crypto_quote_volume_window),
            max_missing_day_rate=float(settings.crypto_max_missing_day_rate),
            max_stale_days=int(settings.crypto_max_stale_days),
            min_minority_class_rate=float(settings.crypto_min_minority_class_rate),
            walk_forward_folds=int(settings.crypto_walk_forward_folds),
            walk_forward_initial_fraction=float(settings.crypto_walk_forward_initial_fraction),
            min_median_roc_auc=float(settings.crypto_min_median_roc_auc),
            min_median_balanced_accuracy=float(settings.crypto_min_median_balanced_accuracy),
            min_folds_beating_baseline=int(settings.crypto_min_folds_beating_baseline),
        )


@dataclass(frozen=True)
class CryptoEligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    bars: int
    feature_samples: int
    median_quote_volume: float
    missing_day_rate: float
    stale_days: int
    minority_class_rate: float
    data_start: str
    data_end: str


@dataclass(frozen=True)
class CryptoQualification:
    symbol: str
    approved: bool
    eligibility: CryptoEligibilityResult | None = None
    folds: tuple[FoldMetrics, ...] = ()
    median_roc_auc: float | None = None
    median_balanced_accuracy: float | None = None
    folds_beating_baseline: int = 0
    rejection_reasons: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class CryptoQualificationReport:
    generated_at: str
    universe_name: str
    universe_retrieved_at: str
    universe_source: str
    exchange: str
    model: str
    timeframe: str
    thresholds: CryptoThresholds
    results: tuple[CryptoQualification, ...] = field(default_factory=tuple)

    @property
    def approved_symbols(self) -> tuple[str, ...]:
        return tuple(result.symbol for result in self.results if result.approved)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                asdict(self),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
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
            "median_quote_volume",
            "missing_day_rate",
            "stale_days",
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
                        "median_quote_volume": (
                            eligibility.median_quote_volume if eligibility else ""
                        ),
                        "missing_day_rate": (eligibility.missing_day_rate if eligibility else ""),
                        "stale_days": eligibility.stale_days if eligibility else "",
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
    def read_json(cls, path: Path) -> CryptoQualificationReport:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["thresholds"] = CryptoThresholds(**payload["thresholds"])
        payload["results"] = tuple(
            CryptoQualification(
                **{
                    **item,
                    "eligibility": (
                        CryptoEligibilityResult(
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
