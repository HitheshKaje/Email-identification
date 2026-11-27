/// Models supporting the User Security & Privacy Dashboard inside Settings.
library;

class SessionInfo {
  const SessionInfo({
    required this.id,
    required this.deviceInfo,
    required this.createdAt,
    required this.lastActiveAt,
    required this.expiresAt,
    this.ipAddress,
    this.isCurrent = false,
  });

  final String id;
  final String deviceInfo;
  final String? ipAddress;
  final DateTime createdAt;
  final DateTime lastActiveAt;
  final DateTime expiresAt;
  final bool isCurrent;

  factory SessionInfo.fromJson(Map<String, dynamic> json) {
    return SessionInfo(
      id: (json['id'] ?? '').toString(),
      deviceInfo: (json['device_info'] ?? 'Unknown Device').toString(),
      ipAddress: json['ip_address']?.toString(),
      createdAt: DateTime.tryParse((json['created_at'] ?? '').toString()) ??
          DateTime.now(),
      lastActiveAt:
          DateTime.tryParse((json['last_active_at'] ?? '').toString()) ??
              DateTime.now(),
      expiresAt: DateTime.tryParse((json['expires_at'] ?? '').toString()) ??
          DateTime.now(),
      isCurrent: json['is_current'] == true,
    );
  }
}

class MfaSetupInfo {
  const MfaSetupInfo({
    required this.secret,
    required this.provisioningUri,
    required this.recoveryCodes,
  });

  final String secret;
  final String provisioningUri;
  final List<String> recoveryCodes;

  factory MfaSetupInfo.fromJson(Map<String, dynamic> json) {
    final codesRaw = json['recovery_codes'];
    final codes = codesRaw is List
        ? codesRaw.map((e) => e.toString()).toList()
        : const <String>[];
    return MfaSetupInfo(
      secret: (json['secret'] ?? '').toString(),
      provisioningUri: (json['provisioning_uri'] ?? '').toString(),
      recoveryCodes: codes,
    );
  }
}

class SecurityEventItem {
  const SecurityEventItem({
    required this.id,
    required this.eventType,
    required this.severity,
    required this.summary,
    required this.createdAt,
    this.ipAddress,
    this.alert = false,
  });

  final String id;
  final String eventType;
  final String severity;
  final String summary;
  final String? ipAddress;
  final DateTime createdAt;
  final bool alert;

  factory SecurityEventItem.fromJson(Map<String, dynamic> json) {
    return SecurityEventItem(
      id: (json['id'] ?? '').toString(),
      eventType: (json['event_type'] ?? '').toString(),
      severity: (json['severity'] ?? 'info').toString(),
      summary: (json['summary'] ?? '').toString(),
      ipAddress: json['ip_address']?.toString(),
      createdAt: DateTime.tryParse((json['created_at'] ?? '').toString()) ??
          DateTime.now(),
      alert: json['alert'] == true,
    );
  }
}

class PrivacyOverview {
  const PrivacyOverview({
    required this.dataRetentionDays,
    required this.gmailScope,
    required this.emailsStored,
    required this.connectedAccounts,
    required this.notificationsStored,
    required this.encryptionAtRest,
    required this.limitedUseNotice,
  });

  final int dataRetentionDays;
  final String gmailScope;
  final int emailsStored;
  final int connectedAccounts;
  final int notificationsStored;
  final String encryptionAtRest;
  final String limitedUseNotice;

  factory PrivacyOverview.fromJson(Map<String, dynamic> json) {
    return PrivacyOverview(
      dataRetentionDays: (json['data_retention_days'] is num)
          ? (json['data_retention_days'] as num).toInt()
          : 180,
      gmailScope: (json['gmail_scope'] ?? '').toString(),
      emailsStored: (json['emails_stored'] is num)
          ? (json['emails_stored'] as num).toInt()
          : 0,
      connectedAccounts: (json['connected_accounts'] is num)
          ? (json['connected_accounts'] as num).toInt()
          : 0,
      notificationsStored: (json['notifications_stored'] is num)
          ? (json['notifications_stored'] as num).toInt()
          : 0,
      encryptionAtRest: (json['encryption_at_rest'] ?? '').toString(),
      limitedUseNotice: (json['limited_use_notice'] ?? '').toString(),
    );
  }
}
