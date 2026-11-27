"""Phase 5 tests for hybrid email classification, entity extraction, edge cases, and feedback loop."""

from datetime import datetime, timezone
import pytest
from app.classification.baseline import KeywordContextBaseline
from app.classification.entity_extractor import extract_company_and_role
from app.classification.nlp_classifier import JobMailClassifier
from app.models.enums import EmailCategory
from app.services.classification_service import ClassificationService


@pytest.mark.parametrize(
    ("subject", "body", "sender", "expected"),
    [
        (
            "Shortlisted for Interview at Infosys",
            "Congratulations! You have been shortlisted for the Software Developer interview at Infosys.",
            "Infosys Talent Acquisition <careers@infosys.com>",
            EmailCategory.INTERVIEW,
        ),
        (
            "Internship Opportunity for Python Developers",
            "We are pleased to announce internship opportunities for Python developers this summer.",
            "TechCorp Campus <internships@techcorp.io>",
            EmailCategory.INTERNSHIP,
        ),
        (
            "We are hiring: Backend Engineer at Razorpay",
            "Our engineering team at Razorpay is hiring a full-time Backend Engineer. Submit your application today.",
            "Razorpay Careers <careers@razorpay.com>",
            EmailCategory.JOB,
        ),
        (
            "Online Assessment Invitation - HackerRank",
            "Complete your 90-minute HackerRank coding assessment before Sunday.",
            "HackerRank <noreply@hackerrank.com>",
            EmailCategory.ASSESSMENT,
        ),
        (
            "Campus Placement Drive 2027 - Register Now",
            "The Training and Placement Cell announces the upcoming campus recruitment drive by Deloitte.",
            "Placement Cell <placement@college.edu>",
            EmailCategory.RECRUITMENT_DRIVE,
        ),
        (
            "Official Offer Letter: Software Engineer at Zoho",
            "Congratulations! We are pleased to offer you the position of Software Engineer. Review and sign your offer letter.",
            "Zoho HR <offers@zoho.com>",
            EmailCategory.OFFER_LETTER,
        ),
        (
            "Application Received: Software Engineer at Stripe",
            "Thank you for applying to Stripe. Your application status is currently under review by the hiring manager.",
            "Stripe Careers <no-reply@greenhouse.io>",
            EmailCategory.APPLICATION_UPDATE,
        ),
        (
            "Update on your application at Google",
            "Thank you for interviewing with us. Unfortunately, we regret to inform you that we will not be moving forward with your candidacy.",
            "Google Recruiting <recruiting@google.com>",
            EmailCategory.REJECTION,
        ),
        (
            "Electricity Bill Ready",
            "Your electricity bill is ready for payment.",
            "Power Utility <billing@power.example>",
            EmailCategory.OTHER,
        ),
    ],
)
def test_classifier_handles_all_categories(subject, body, sender, expected):
    classifier = JobMailClassifier()
    out = classifier.classify(subject, body, sender)
    assert out.category == expected
    assert 0.0 <= out.confidence <= 1.0


@pytest.mark.parametrize(
    ("subject", "body", "sender"),
    [
        (
            "Good job on completing your 7-day fitness streak!",
            "You did a great job hitting your step goals every day this week.",
            "FitTrack <noreply@fittrack.example>",
        ),
        (
            "Download our free interview prep eBook - Sale ends soon",
            "Get 40% discount on our interview questions guide. Buy today!",
            "StudyDeals <promo@studydeals.example>",
        ),
        (
            "Exclusive 30% discount offer on laptops",
            "Limited-time holiday offer ends tonight! Use promo code SAVE30.",
            "MegaMart <deals@megamart.example>",
        ),
        (
            "Home energy assessment report is ready",
            "Review your annual electricity usage assessment report with savings recommendations.",
            "SolarCare <info@solarcare.example>",
        ),
    ],
)
def test_isolated_keywords_do_not_trigger_false_positives(subject, body, sender):
    baseline = KeywordContextBaseline().evaluate(subject, body, sender)
    assert baseline.category == EmailCategory.OTHER

    classifier = JobMailClassifier()
    out = classifier.classify(subject, body, sender)
    assert out.category == EmailCategory.OTHER


def test_entity_extractor_identifies_company_and_role():
    company, role = extract_company_and_role(
        "Interview Invitation",
        "Congratulations! You have been shortlisted for the Software Developer interview at Infosys.",
        "Infosys Talent Acquisition <careers@infosys.com>",
    )
    assert company == "Infosys"
    assert role == "Software Developer"


@pytest.mark.asyncio
async def test_classification_predict_endpoint_and_feedback_retraining(
    client, test_settings
):
    ac, db = client
    reg = await ac.post(
        "/auth/register",
        json={"name": "ML User", "email": "ml@example.com", "password": "StrongPassword123!"},
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Predict via REST API
    pred = await ac.post(
        "/classification/predict",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "subject": "Interview Invitation - Infosys",
            "body": "Congratulations! You have been shortlisted for the Software Developer interview at Infosys.",
            "sender": "Infosys Careers <careers@infosys.com>",
        },
    )
    assert pred.status_code == 200
    body = pred.json()
    assert body["category"] == "INTERVIEW"
    assert body["company_name"] == "Infosys"
    assert body["job_role"] == "Software Developer"
    assert body["confidence"] > 0.5

    # Submit user correction feedback and verify feedback stores context for retraining
    ins = await db.emails.insert_one(
        {
            "user_id": user_id,
            "account_id": "acc-1",
            "gmail_message_id": "ml-msg-1",
            "sender": "Careers <hr@company.io>",
            "subject": "Final selection update for Cloud Engineer",
            "body_preview": "Welcome aboard, please review attached onboarding steps.",
            "received_at": datetime.now(timezone.utc),
            "category": EmailCategory.APPLICATION_UPDATE.value,
            "confidence": 0.7,
            "company_name": None,
            "job_role": "Cloud Engineer",
            "is_read": False,
        }
    )
    email_id = str(ins.inserted_id)

    fb = await ac.post(
        "/classification/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email_id": email_id,
            "corrected_category": EmailCategory.OFFER_LETTER.value,
        },
    )
    assert fb.status_code == 200
    fb_doc = await db.classification_feedback.find_one({"email_id": email_id})
    assert fb_doc is not None
    assert fb_doc["corrected_category"] == "OFFER_LETTER"
    assert "subject" not in fb_doc
    assert fb_doc.get("encrypted_subject")

    total = await ClassificationService(db, test_settings).retrain_from_feedback(
        user_id=user_id, save_to_disk=False
    )
    assert total > 100
