"""Standalone prediction interface for JobMail's trained NLP email classifier."""

from pathlib import Path
import joblib
from sklearn.pipeline import Pipeline
from ml.training.train_model import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    build_pipeline,
    format_email_features,
    load_training_dataset,
)


class EmailPredictor:
    """Loads or lazily trains the TF-IDF + LogisticRegression classifier."""

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH) -> None:
        self._model_path = model_path
        self._pipeline: Pipeline | None = None

    def _ensure_loaded(self) -> Pipeline:
        if self._pipeline is not None:
            return self._pipeline
        if self._model_path.exists():
            self._pipeline = joblib.load(self._model_path)
            return self._pipeline
        texts, labels = load_training_dataset(DEFAULT_DATASET_PATH)
        pipeline = build_pipeline()
        pipeline.fit(texts, labels)
        self._pipeline = pipeline
        return pipeline

    def predict(
        self, subject: str, body: str, sender: str = ""
    ) -> tuple[str, float, dict[str, float]]:
        pipeline = self._ensure_loaded()
        text = format_email_features(subject, body, sender)
        probs = pipeline.predict_proba([text])[0]
        classes = [str(c) for c in pipeline.classes_]
        prob_map = {cls: float(prob) for cls, prob in zip(classes, probs)}
        best_cls = max(prob_map, key=lambda key: prob_map[key])
        return best_cls, prob_map[best_cls], prob_map
