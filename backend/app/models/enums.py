"""Domain enumerations shared across backend models, database queries, and API routes."""

from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class EmailCategory(str, Enum):
    JOB = "JOB"
    INTERNSHIP = "INTERNSHIP"
    INTERVIEW = "INTERVIEW"
    ASSESSMENT = "ASSESSMENT"
    RECRUITMENT_DRIVE = "RECRUITMENT_DRIVE"
    OFFER_LETTER = "OFFER_LETTER"
    APPLICATION_UPDATE = "APPLICATION_UPDATE"
    REJECTION = "REJECTION"
    OTHER = "OTHER"

    @classmethod
    def job_categories(cls) -> list["EmailCategory"]:
        return [
            cls.JOB,
            cls.INTERNSHIP,
            cls.INTERVIEW,
            cls.ASSESSMENT,
            cls.RECRUITMENT_DRIVE,
            cls.OFFER_LETTER,
            cls.APPLICATION_UPDATE,
            cls.REJECTION,
        ]


class AccountSyncStatus(str, Enum):
    SYNCED = "SYNCED"
    SYNCING = "SYNCING"
    PENDING = "PENDING"
    ERROR = "ERROR"
    REVOKED = "REVOKED"
