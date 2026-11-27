# JobMail – Google OAuth 2.0 Restricted Scope Production Compliance Guide (Phase 15)

## 1. Current Scope Classification
JobMail requests strictly one read-only Gmail scope:

- `https://www.googleapis.com/auth/gmail.readonly`

Under Google API Services policy, `gmail.readonly` is a **Restricted Scope**. Because JobMail's FastAPI backend exchanges authorization codes, stores encrypted OAuth refresh tokens, and fetches/classifies email metadata and previews server-side:

1. **Google OAuth App Verification is MANDATORY** before moving out of `Testing` publishing status to allow arbitrary external Google accounts (`> 100` test users or public sign-ups).
2. **Independent Security Assessment (CASA Tier 2 / Tier 3) is MANDATORY** via an App Defense Alliance (ADA) authorized lab to obtain an annual **Letter of Validation (LOV)**.

> **Current Status:** Application has **NOT** yet been submitted to or approved by Google Trust & Safety or an ADA CASA lab. It is currently suitable for internal/Test-User development only until verification & CASA assessment are completed.

## 2. Google Cloud & Domain Requirements
1. **Verified Custom Domain:** Verify domain ownership in Google Search Console for your homepage (`https://yourdomain.com`), privacy policy (`https://yourdomain.com/privacy`), terms of service, and OAuth callback domain (`https://api.yourdomain.com`). Do **not** use `localhost` URLs in production.
2. **OAuth Consent Screen Branding:**
   - Accurate public app name (`JobMail`), verified support email, official logo matching the published homepage, and authorized domains matching `GOOGLE_REDIRECT_URI`.
3. **Google API Services User Data Policy & Limited Use Compliance:**
   - **Data Minimization:** JobMail stores sanitized/encrypted previews, sender, subject, timestamps, and company/role classifications—not raw attachments or arbitrary third-party sharing.
   - **No Cross-User AI Training:** User feedback corrections are isolated per user (`ClassificationService.retrain_from_feedback(user_id=...)`) and are never aggregated across users into a shared generalized ML model.
   - **Revocation & Erasure:** Disconnecting an account revokes tokens with Google (`oauth2.googleapis.com/revoke`) and purges synced email data; `DELETE /privacy/account` permanently deletes all user and Gmail records.

## 3. Required Public Documentation & Submission Materials
Before clicking **Publish App** in Google Auth Platform:
1. **Public Homepage (`https://yourdomain.com`):** Explains JobMail's recruitment inbox purpose clearly.
2. **Public Privacy Policy (`https://yourdomain.com/privacy`):** Explicitly discloses:
   - Exact access to `gmail.readonly` data (subjects, senders, timestamps, sanitized previews)
   - Purpose limitation (classifying job/interview/offer emails for the authenticated user only)
   - Encryption at rest (`MultiFernet`), non-sharing with third parties, retention controls, and how to revoke access & delete data
   - Explicit affirmation adhering to the **Google API Services User Data Policy, including the Limited Use requirements**
3. **YouTube Unlisted Verification Demo Video:** Must visibly show:
   - OAuth Client ID visible in the browser URL bar during consent
   - Consent screen showing `gmail.readonly` scope prompt
   - Returning to JobMail Connected Accounts and displaying fetched/classified job emails
4. **CASA Assessment Preparation:**
   - Retain `pip-audit` reports, `pytest` OWASP security suite results, `flutter analyze`, `deploy/nginx.conf` TLS headers, and `backend/app/core/config.py` environment protections as evidence for your ADA lab SAQ & DAST scan.
