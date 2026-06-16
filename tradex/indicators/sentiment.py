from __future__ import annotations

from tradex.strategy.schema import NewsGateConfig

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _VADER_AVAILABLE = True
except ImportError:
    _VADER_AVAILABLE = False


def assess_sentiment(
    headlines: list[str],
    cfg: NewsGateConfig | None = None,
) -> NewsAssessment:
    if cfg is None:
        cfg = NewsGateConfig()

    if not headlines or not _VADER_AVAILABLE:
        return NewsAssessment(
            compound=0.0,
            positive_count=0,
            negative_count=0,
            neutral_count=0,
            article_count=0,
        )

    analyzer = SentimentIntensityAnalyzer()
    scores = [analyzer.polarity_scores(h)["compound"] for h in headlines]

    positive = sum(1 for s in scores if s >= 0.05)
    negative = sum(1 for s in scores if s <= -0.05)
    neutral = len(scores) - positive - negative
    compound = sum(scores) / len(scores) if scores else 0.0

    return NewsAssessment(
        compound=compound,
        positive_count=positive,
        negative_count=negative,
        neutral_count=neutral,
        article_count=len(scores),
    )


class NewsAssessment:
    __slots__ = ("compound", "positive_count", "negative_count", "neutral_count", "article_count")

    def __init__(
        self,
        compound: float,
        positive_count: int,
        negative_count: int,
        neutral_count: int,
        article_count: int,
    ) -> None:
        self.compound = compound
        self.positive_count = positive_count
        self.negative_count = negative_count
        self.neutral_count = neutral_count
        self.article_count = article_count

    @property
    def bullish_gate(self) -> bool:
        # No articles → don't veto (pass-through)
        if self.article_count == 0:
            return True
        return self.compound >= 0.05

    @property
    def bearish_gate(self) -> bool:
        if self.article_count == 0:
            return True
        return self.compound <= -0.05

    @property
    def __dict__(self) -> dict:
        return {
            "compound": self.compound,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "neutral_count": self.neutral_count,
            "article_count": self.article_count,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
