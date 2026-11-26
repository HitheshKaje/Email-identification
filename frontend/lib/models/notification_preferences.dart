/// User alert preferences per recruitment category.
class NotificationPreferences {
  const NotificationPreferences({
    this.pushEnabled = true,
    this.jobOpportunities = true,
    this.internshipOpportunities = true,
    this.interviewInvitations = true,
    this.onlineAssessments = true,
    this.recruitmentDrives = true,
    this.offerLetters = true,
    this.applicationUpdates = false,
  });

  final bool pushEnabled;
  final bool jobOpportunities;
  final bool internshipOpportunities;
  final bool interviewInvitations;
  final bool onlineAssessments;
  final bool recruitmentDrives;
  final bool offerLetters;
  final bool applicationUpdates;

  NotificationPreferences copyWith({
    bool? pushEnabled,
    bool? jobOpportunities,
    bool? internshipOpportunities,
    bool? interviewInvitations,
    bool? onlineAssessments,
    bool? recruitmentDrives,
    bool? offerLetters,
    bool? applicationUpdates,
  }) {
    return NotificationPreferences(
      pushEnabled: pushEnabled ?? this.pushEnabled,
      jobOpportunities: jobOpportunities ?? this.jobOpportunities,
      internshipOpportunities:
          internshipOpportunities ?? this.internshipOpportunities,
      interviewInvitations: interviewInvitations ?? this.interviewInvitations,
      onlineAssessments: onlineAssessments ?? this.onlineAssessments,
      recruitmentDrives: recruitmentDrives ?? this.recruitmentDrives,
      offerLetters: offerLetters ?? this.offerLetters,
      applicationUpdates: applicationUpdates ?? this.applicationUpdates,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'push_enabled': pushEnabled,
      'job_opportunities': jobOpportunities,
      'internship_opportunities': internshipOpportunities,
      'interview_invitations': interviewInvitations,
      'online_assessments': onlineAssessments,
      'recruitment_drives': recruitmentDrives,
      'offer_letters': offerLetters,
      'application_updates': applicationUpdates,
    };
  }

  factory NotificationPreferences.fromJson(Map<String, dynamic> json) {
    return NotificationPreferences(
      pushEnabled: json['push_enabled'] as bool? ?? true,
      jobOpportunities: json['job_opportunities'] as bool? ?? true,
      internshipOpportunities:
          json['internship_opportunities'] as bool? ?? true,
      interviewInvitations: json['interview_invitations'] as bool? ?? true,
      onlineAssessments: json['online_assessments'] as bool? ?? true,
      recruitmentDrives: json['recruitment_drives'] as bool? ?? true,
      offerLetters: json['offer_letters'] as bool? ?? true,
      applicationUpdates: json['application_updates'] as bool? ?? false,
    );
  }
}
