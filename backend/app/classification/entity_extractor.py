"""Heuristic extraction of company names and job roles from recruitment emails."""

import re

_GENERIC_DOMAINS: set[str] = {
    "gmail",
    "googlemail",
    "yahoo",
    "outlook",
    "hotmail",
    "live",
    "icloud",
    "proton",
    "protonmail",
    "greenhouse",
    "lever",
    "myworkday",
    "workday",
    "hackerrank",
    "codility",
    "codesignal",
    "mettl",
    "hirevue",
    "naukri",
    "linkedin",
    "indeed",
    "example",
    "university",
    "college",
    "institute",
}

_STOP_WORDS: set[str] = {
    "the",
    "our",
    "your",
    "this",
    "that",
    "next",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "today",
    "tomorrow",
    "zoom",
    "teams",
    "microsoft teams",
    "google meet",
    "online",
    "remote",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "pune",
    "india",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "python",
    "java",
    "react",
    "flutter",
    "sql",
    "aws",
    "cloud",
}

_SENDER_SUFFIX_RE = re.compile(
    r"\b(talent acquisition|university recruiting|student programs|early careers|people ops|hiring team|campus hiring|campus|careers|recruiting|recruitment|talent|jobs|hr|onboarding|cell|office|assessments|team)\b",
    re.IGNORECASE,
)

_COMPANY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:interview|role|position|opening|opportunity|internship|offer|application|candidacy)\s+(?:at|with|from|to)\s+([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,2})"
    ),
    re.compile(
        r"\b(?:at|from|with)\s+([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*)?)(?=[.,!?\s]|$)"
    ),
    re.compile(
        r"^([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,1})\s+(?:is\s+hiring|has\s+posted|is\s+offering|is\s+expanding)\b",
        re.MULTILINE,
    ),
)

_ROLE_NOUNS = (
    r"(?:Software|Backend|Frontend|Full[\s-]?Stack|Mobile|Flutter|Python|Java|React|"
    r"Machine\s+Learning|ML|Data|Cloud|DevOps|QA|Automation|Product|UI/UX|"
    r"Cybersecurity|Associate|Graduate|Trainee|Senior|Junior|Systems|Embedded)"
    r"(?:\s+[A-Za-z0-9/.\-]+){0,3}\s+"
    r"(?:Developer|Engineer|Intern|Analyst|Scientist|Designer|Manager|Architect|Associate|Consultant|Trainee|Specialist|Staff)"
)

_ROLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\b(?:for\s+(?:the|our|a|an)\s+|position\s+of\s+|hiring\s+(?:a|an)?\s*|apply\s+for\s+(?:the|our|a|an)?\s*)({_ROLE_NOUNS})(?=\s+(?:interview|role|position|opening|internship|opportunity|at|with|on|in|for|program|cohort)\b|[.,!?\s]|$)",
        re.IGNORECASE,
    ),
    re.compile(rf"\b({_ROLE_NOUNS})\b", re.IGNORECASE),
)

_SENDER_EMAIL_RE = re.compile(r"<([^>]+)>")


def extract_company_and_role(
    subject: str, body: str, sender: str = ""
) -> tuple[str | None, str | None]:
    """Extract likely company name and job role from subject, body, and sender."""
    text = f"{subject}\n{body}"
    company = _extract_company(text, sender)
    role = _extract_role(subject, body)
    return company, role


def _extract_company(text: str, sender: str) -> str | None:
    for pattern in _COMPANY_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1).strip(" .,-")
            if _is_valid_company(candidate):
                return candidate

    # Try sender display name (e.g., "Infosys Talent Acquisition <careers@infosys.com>")
    display_name = _SENDER_EMAIL_RE.sub("", sender).replace('"', "").strip()
    cleaned_display = _SENDER_SUFFIX_RE.sub("", display_name).strip(" -|,:")
    if cleaned_display and _is_valid_company(cleaned_display):
        return cleaned_display

    # Fallback to sender email domain (e.g., careers@infosys.com -> Infosys)
    email_match = _SENDER_EMAIL_RE.search(sender)
    email_addr = email_match.group(1) if email_match else sender.strip()
    if "@" in email_addr:
        domain_part = email_addr.split("@", 1)[1].lower()
        labels = [lbl for lbl in domain_part.split(".") if lbl]
        if len(labels) >= 2:
            sld = labels[-2]
            if sld in ("co", "ac", "com", "org", "edu") and len(labels) >= 3:
                sld = labels[-3]
            if sld not in _GENERIC_DOMAINS and len(sld) >= 2:
                return sld.capitalize()
    return None


def _is_valid_company(candidate: str) -> bool:
    if not candidate or len(candidate) < 2 or len(candidate) > 40:
        return False
    lower = candidate.lower()
    if lower in _STOP_WORDS:
        return False
    if lower in _GENERIC_DOMAINS:
        return False
    if any(
        bad in lower
        for bad in (
            "software",
            "developer",
            "engineer",
            "intern",
            "interview",
            "application",
            "assessment",
            "opportunity",
            "placement",
            "campus",
            "hiring team",
            "recruiting",
            "talent",
        )
    ):
        return False
    return True


def _extract_role(subject: str, body: str) -> str | None:
    for source in (subject, body):
        for pattern in _ROLE_PATTERNS:
            match = pattern.search(source)
            if match:
                raw = re.sub(r"\s+", " ", match.group(1)).strip(" .,-:")
                if 4 <= len(raw) <= 60:
                    return _clean_role_casing(raw)
    return None


def _clean_role_casing(role: str) -> str:
    acronyms = {"UI/UX", "ML", "QA", "SQL", "AWS", "API", "SDE"}
    words = []
    for word in role.split():
        upper = word.upper()
        if upper in acronyms:
            words.append(upper)
        else:
            words.append(word[0].upper() + word[1:])
    return " ".join(words)
