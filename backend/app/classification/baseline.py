"""Context-aware keyword baseline classifier for recruitment emails."""

from dataclasses import dataclass
import re
from app.models.enums import EmailCategory

_NOISE_PHRASES: tuple[str, ...] = (
    "electricity bill",
    "water bill",
    "gas bill",
    "power bill",
    "utility bill",
    "ready for payment",
    "amount due",
    "credit card statement",
    "e-statement",
    "bank statement",
    "has shipped",
    "out for delivery",
    "track your shipment",
    "parcel status",
    "food order",
    "flight booking",
    "boarding pass",
    "netbanking transaction",
    "verification code",
    "password reset",
    "security alert",
    "new sign-in",
    "fitness streak",
    "step goals",
    "promo code",
    "discount offer",
    "holiday offer",
    "offer ends tonight",
    "annual plan",
    "buy today",
    "ebook",
    "energy assessment report",
)

_CATEGORY_PHRASES: dict[EmailCategory, tuple[tuple[str, float], ...]] = {
    EmailCategory.INTERVIEW: (
        ("shortlisted for", 2.2),
        ("interview invitation", 2.6),
        ("invited for an interview", 2.4),
        ("invite you to a", 1.5),
        ("technical interview", 2.4),
        ("hr interview", 2.3),
        ("phone screen", 2.1),
        ("system design interview", 2.4),
        ("managerial round", 2.1),
        ("panel interview", 2.3),
        ("interview schedule", 2.2),
        ("interview slot", 2.2),
        ("calendar invite", 1.7),
        ("interview at", 2.1),
        ("scheduled interview", 2.2),
        ("video interview", 2.1),
        ("rescheduled interview", 2.2),
    ),
    EmailCategory.OFFER_LETTER: (
        ("offer letter", 2.8),
        ("official offer", 2.7),
        ("offer of employment", 2.8),
        ("employment offer", 2.6),
        ("pleased to offer you", 2.7),
        ("delighted to offer you", 2.7),
        ("extend a full-time", 2.3),
        ("pre-placement offer", 2.6),
        ("compensation package", 2.2),
        ("joining date", 1.9),
        ("salary breakdown", 2.1),
        ("employment agreement", 2.3),
        ("accept your offer", 2.3),
    ),
    EmailCategory.ASSESSMENT: (
        ("online assessment", 2.6),
        ("coding assessment", 2.7),
        ("coding test", 2.5),
        ("technical assessment", 2.6),
        ("hackerrank", 2.5),
        ("codility", 2.5),
        ("codesignal", 2.5),
        ("mettl", 2.4),
        ("hirevue", 2.4),
        ("shl", 2.0),
        ("assessment link", 2.5),
        ("test link", 2.2),
        ("take-home", 2.2),
        ("coding challenge", 2.3),
        ("aptitude and coding", 2.5),
        ("online test", 2.2),
        ("coding round", 2.1),
    ),
    EmailCategory.RECRUITMENT_DRIVE: (
        ("recruitment drive", 2.7),
        ("placement drive", 2.7),
        ("campus drive", 2.6),
        ("hiring drive", 2.6),
        ("walk-in recruitment", 2.6),
        ("pooled campus", 2.5),
        ("placement cell", 2.4),
        ("training and placement", 2.5),
        ("pre-placement talk", 2.6),
        ("placement notification", 2.5),
        ("off-campus hiring", 2.5),
        ("off-campus placement", 2.6),
        ("career fair", 2.2),
        ("hiring event", 2.1),
    ),
    EmailCategory.INTERNSHIP: (
        ("internship opportunity", 2.6),
        ("internship opportunities", 2.6),
        ("internship program", 2.5),
        ("summer internship", 2.6),
        ("winter internship", 2.6),
        ("paid internship", 2.5),
        ("intern role", 2.3),
        ("intern opening", 2.4),
        ("software engineering intern", 2.5),
        ("developer intern", 2.4),
        ("monthly stipend", 1.9),
        ("summer intern", 2.3),
    ),
    EmailCategory.REJECTION: (
        ("regret to inform", 2.8),
        ("not moving forward", 2.8),
        ("not to move forward", 2.8),
        ("cannot move forward", 2.7),
        ("not selected", 2.7),
        ("not shortlisted", 2.7),
        ("no longer under consideration", 2.8),
        ("position has now been filled", 2.6),
        ("position filled", 2.4),
        ("unable to offer you", 2.6),
        ("unable to extend an offer", 2.6),
        ("other candidates", 2.2),
        ("application was unsuccessful", 2.8),
        ("will not be advancing", 2.6),
        ("will not be proceeding", 2.7),
    ),
    EmailCategory.APPLICATION_UPDATE: (
        ("application received", 2.6),
        ("received your application", 2.6),
        ("thank you for applying", 2.3),
        ("submitting your application", 2.3),
        ("application status", 2.2),
        ("under review", 2.3),
        ("under evaluation", 2.3),
        ("moved to hiring manager", 2.5),
        ("application progress", 2.3),
        ("application submitted", 2.5),
        ("background verification", 2.2),
        ("candidate profile", 1.8),
        ("application reference", 2.2),
    ),
    EmailCategory.JOB: (
        ("we are hiring", 2.2),
        ("is hiring", 2.1),
        ("actively hiring", 2.3),
        ("job opportunity", 2.4),
        ("job opening", 2.4),
        ("engineer opening", 2.2),
        ("developer opening", 2.2),
        ("engineer role", 1.9),
        ("developer role", 1.9),
        ("job alert", 2.2),
        ("full-time opening", 2.4),
        ("full-time position", 2.3),
        ("full-time role", 2.2),
        ("reaching out regarding", 1.9),
        ("submit your application", 1.7),
        ("apply for", 1.5),
        ("job description", 2.0),
        ("matching your resume", 2.3),
        ("invite you to apply", 2.3),
    ),
}

_RECRUITING_SENDER_RE = re.compile(
    r"(careers|recruiting|recruitment|talent|jobs|hiring|placement|tpo|internships|offers|greenhouse\.io|lever\.co|myworkday\.com|hackerrank|codility|codesignal)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BaselineResult:
    category: EmailCategory
    scores: dict[EmailCategory, float]
    best_job_score: float
    noise_hits: int
    has_recruiting_sender: bool

    @property
    def is_non_job_noise(self) -> bool:
        return self.noise_hits > 0 and self.best_job_score < 2.2


class KeywordContextBaseline:
    """Evaluates contextual multi-word phrases rather than isolated words."""

    def evaluate(
        self, subject: str, body: str, sender: str = ""
    ) -> BaselineResult:
        subject_lower = (subject or "").lower()
        body_lower = (body or "").lower()
        combined = f"{subject_lower}\n{body_lower}"

        noise_hits = sum(1 for phrase in _NOISE_PHRASES if phrase in combined)
        has_recruiting_sender = bool(_RECRUITING_SENDER_RE.search(sender or ""))

        scores: dict[EmailCategory, float] = {
            cat: 0.0 for cat in EmailCategory.job_categories()
        }

        for category, phrases in _CATEGORY_PHRASES.items():
            total = 0.0
            for phrase, weight in phrases:
                if phrase in subject_lower:
                    total += weight * 1.35
                elif phrase in body_lower:
                    total += weight
            if total > 0 and has_recruiting_sender:
                total += 0.35
            scores[category] = total

        best_cat = max(scores, key=lambda c: scores[c])
        best_score = scores[best_cat]

        if best_score < 1.6 or (noise_hits > 0 and best_score < 2.2):
            predicted = EmailCategory.OTHER
        else:
            predicted = best_cat

        return BaselineResult(
            category=predicted,
            scores=scores,
            best_job_score=best_score,
            noise_hits=noise_hits,
            has_recruiting_sender=has_recruiting_sender,
        )
