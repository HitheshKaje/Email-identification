"""Hybrid TF-IDF + LogisticRegression and context-aware recruitment email classifier."""

from dataclasses import dataclass
import json
from pathlib import Path
import threading
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from app.classification.baseline import KeywordContextBaseline
from app.classification.entity_extractor import extract_company_and_role
from app.models.enums import EmailCategory

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "ml" / "dataset" / "training_emails.json"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "email_classifier.joblib"


@dataclass(frozen=True)
class ClassificationOutput:
    category: EmailCategory
    confidence: float
    company_name: str | None
    job_role: str | None


def _format_features(subject: str, body: str, sender: str = "") -> str:
    clean_subject = (subject or "").strip()
    clean_sender = (sender or "").strip()
    clean_body = (body or "").strip()
    return f"{clean_subject} {clean_subject} | sender: {clean_sender} | {clean_body}".strip()


def _build_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 3),
                    sublinear_tf=True,
                    min_df=1,
                    max_features=12000,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    C=5.0,
                    random_state=42,
                ),
            ),
        ]
    )


class JobMailClassifier:
    """Combines TF-IDF + LogisticRegression with context guardrails and entity extraction."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        dataset_path: Path = DEFAULT_DATASET_PATH,
    ) -> None:
        self._model_path = model_path
        self._dataset_path = dataset_path
        self._baseline = KeywordContextBaseline()
        self._pipeline: Pipeline | None = None
        self._lock = threading.Lock()

    def _get_pipeline(self) -> Pipeline:
        if self._pipeline is not None:
            return self._pipeline
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            if self._model_path.exists():
                self._pipeline = joblib.load(self._model_path)
            else:
                self._pipeline = self._train_from_dataset()
            return self._pipeline

    def _train_from_dataset(
        self, extra_samples: list[dict[str, str]] | None = None
    ) -> Pipeline:
        raw = json.loads(self._dataset_path.read_text(encoding="utf-8"))
        if extra_samples:
            raw = list(raw) + list(extra_samples)
        texts = [
            _format_features(
                row.get("subject", ""),
                row.get("body", ""),
                row.get("sender", ""),
            )
            for row in raw
        ]
        labels = [str(row["category"]).strip().upper() for row in raw]
        pipeline = _build_pipeline()
        pipeline.fit(texts, labels)
        return pipeline

    def retrain(
        self,
        extra_samples: list[dict[str, str]] | None = None,
        *,
        save_to_disk: bool = True,
    ) -> int:
        """Retrain NLP pipeline incorporating stored user feedback samples."""
        with self._lock:
            raw = json.loads(self._dataset_path.read_text(encoding="utf-8"))
            total_samples = len(raw) + len(extra_samples or [])
            pipeline = self._train_from_dataset(extra_samples=extra_samples)
            if save_to_disk:
                self._model_path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(pipeline, self._model_path)
            self._pipeline = pipeline
            return total_samples

    def classify(
        self, subject: str, body: str, sender: str = ""
    ) -> ClassificationOutput:
        baseline = self._baseline.evaluate(subject, body, sender)
        pipeline = self._get_pipeline()

        feature_text = _format_features(subject, body, sender)
        probs = pipeline.predict_proba([feature_text])[0]
        nlp_probs: dict[EmailCategory, float] = {
            EmailCategory(str(cls_name)): float(prob)
            for cls_name, prob in zip(pipeline.classes_, probs)
        }

        # Guardrail: strong non-job context with no recruitment context stays OTHER.
        if baseline.is_non_job_noise:
            other_conf = max(nlp_probs.get(EmailCategory.OTHER, 0.0), 0.85)
            return ClassificationOutput(
                category=EmailCategory.OTHER,
                confidence=round(min(other_conf, 0.99), 4),
                company_name=None,
                job_role=None,
            )

        blended: dict[EmailCategory, float] = {}
        for cat in EmailCategory.job_categories():
            nlp_score = nlp_probs.get(cat, 0.0)
            ctx_norm = min(baseline.scores.get(cat, 0.0) / 3.5, 1.0)
            blended[cat] = (0.72 * nlp_score) + (0.28 * ctx_norm)

        best_job_cat = max(blended, key=lambda c: blended[c])
        best_job_score = blended[best_job_cat]
        other_nlp_prob = nlp_probs.get(EmailCategory.OTHER, 0.0)

        if baseline.category == EmailCategory.OTHER and (
            other_nlp_prob >= 0.45 or best_job_score < 0.34
        ):
            return ClassificationOutput(
                category=EmailCategory.OTHER,
                confidence=round(min(max(other_nlp_prob, 0.65), 0.99), 4),
                company_name=None,
                job_role=None,
            )

        confidence = min(max(best_job_score + 0.22, nlp_probs.get(best_job_cat, 0.5)), 0.99)
        company, role = extract_company_and_role(subject, body, sender)
        return ClassificationOutput(
            category=best_job_cat,
            confidence=round(confidence, 4),
            company_name=company,
            job_role=role,
        )


_default_classifier = JobMailClassifier()


def get_classifier() -> JobMailClassifier:
    return _default_classifier
