import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// Recruitment email classification categories supported by JobMail.
enum EmailCategory {
  job,
  internship,
  interview,
  assessment,
  recruitmentDrive,
  offerLetter,
  applicationUpdate,
  rejection,
  other;

  /// The 8 career-relevant categories surfaced in Categories & Job Inbox.
  static const List<EmailCategory> jobCategories = <EmailCategory>[
    EmailCategory.job,
    EmailCategory.internship,
    EmailCategory.interview,
    EmailCategory.assessment,
    EmailCategory.recruitmentDrive,
    EmailCategory.offerLetter,
    EmailCategory.applicationUpdate,
    EmailCategory.rejection,
  ];

  String get apiValue {
    switch (this) {
      case EmailCategory.job:
        return 'JOB';
      case EmailCategory.internship:
        return 'INTERNSHIP';
      case EmailCategory.interview:
        return 'INTERVIEW';
      case EmailCategory.assessment:
        return 'ASSESSMENT';
      case EmailCategory.recruitmentDrive:
        return 'RECRUITMENT_DRIVE';
      case EmailCategory.offerLetter:
        return 'OFFER_LETTER';
      case EmailCategory.applicationUpdate:
        return 'APPLICATION_UPDATE';
      case EmailCategory.rejection:
        return 'REJECTION';
      case EmailCategory.other:
        return 'OTHER';
    }
  }

  String get displayName {
    switch (this) {
      case EmailCategory.job:
        return 'Job Opportunities';
      case EmailCategory.internship:
        return 'Internship Opportunities';
      case EmailCategory.interview:
        return 'Interview Invitations';
      case EmailCategory.assessment:
        return 'Online Assessments';
      case EmailCategory.recruitmentDrive:
        return 'Recruitment Drives';
      case EmailCategory.offerLetter:
        return 'Offer Letters';
      case EmailCategory.applicationUpdate:
        return 'Application Status Updates';
      case EmailCategory.rejection:
        return 'Rejection Notifications';
      case EmailCategory.other:
        return 'Other';
    }
  }

  String get shortLabel {
    switch (this) {
      case EmailCategory.job:
        return 'Job';
      case EmailCategory.internship:
        return 'Internship';
      case EmailCategory.interview:
        return 'Interview';
      case EmailCategory.assessment:
        return 'Assessment';
      case EmailCategory.recruitmentDrive:
        return 'Drive';
      case EmailCategory.offerLetter:
        return 'Offer Letter';
      case EmailCategory.applicationUpdate:
        return 'Status Update';
      case EmailCategory.rejection:
        return 'Rejection';
      case EmailCategory.other:
        return 'Other';
    }
  }

  String get description {
    switch (this) {
      case EmailCategory.job:
        return 'Full-time openings, recruiter outreach, and role matches';
      case EmailCategory.internship:
        return 'Student, graduate, and seasonal internship opportunities';
      case EmailCategory.interview:
        return 'Shortlists, interview invites, and schedule confirmations';
      case EmailCategory.assessment:
        return 'Coding tests, aptitude rounds, and take-home challenges';
      case EmailCategory.recruitmentDrive:
        return 'Campus drives, hiring events, and career fairs';
      case EmailCategory.offerLetter:
        return 'Official job offers, compensation details, and onboarding';
      case EmailCategory.applicationUpdate:
        return 'Submission confirmations and pipeline progress updates';
      case EmailCategory.rejection:
        return 'Application closure and selection outcome notices';
      case EmailCategory.other:
        return 'General or non-recruitment emails';
    }
  }

  IconData get icon {
    switch (this) {
      case EmailCategory.job:
        return Icons.work_outline_rounded;
      case EmailCategory.internship:
        return Icons.school_outlined;
      case EmailCategory.interview:
        return Icons.event_available_outlined;
      case EmailCategory.assessment:
        return Icons.quiz_outlined;
      case EmailCategory.recruitmentDrive:
        return Icons.campaign_outlined;
      case EmailCategory.offerLetter:
        return Icons.verified_outlined;
      case EmailCategory.applicationUpdate:
        return Icons.track_changes_outlined;
      case EmailCategory.rejection:
        return Icons.highlight_off_outlined;
      case EmailCategory.other:
        return Icons.mail_outline_rounded;
    }
  }

  Color get color {
    switch (this) {
      case EmailCategory.job:
        return AppColors.primary;
      case EmailCategory.internship:
        return AppColors.secondary;
      case EmailCategory.interview:
        return AppColors.accentPurple;
      case EmailCategory.assessment:
        return AppColors.accentAmber;
      case EmailCategory.recruitmentDrive:
        return AppColors.accentCyan;
      case EmailCategory.offerLetter:
        return AppColors.accentEmerald;
      case EmailCategory.applicationUpdate:
        return const Color(0xFF4F46E5);
      case EmailCategory.rejection:
        return AppColors.accentRose;
      case EmailCategory.other:
        return const Color(0xFF64748B);
    }
  }

  static EmailCategory fromApi(String? raw) {
    if (raw == null) return EmailCategory.other;
    final normalized = raw.trim().toUpperCase();
    for (final value in EmailCategory.values) {
      if (value.apiValue == normalized) {
        return value;
      }
    }
    return EmailCategory.other;
  }
}
