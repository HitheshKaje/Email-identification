/// Authenticated JobMail user profile and security attributes.
class UserProfile {
  const UserProfile({
    required this.id,
    required this.name,
    required this.email,
    this.createdAt,
    this.emailVerified = false,
    this.mfaEnabled = false,
    this.role = 'user',
    this.lastLoginAt,
    this.lastLoginIp,
    this.dataRetentionDays = 180,
  });

  final String id;
  final String name;
  final String email;
  final DateTime? createdAt;
  final bool emailVerified;
  final bool mfaEnabled;
  final String role;
  final DateTime? lastLoginAt;
  final String? lastLoginIp;
  final int dataRetentionDays;

  UserProfile copyWith({
    String? name,
    String? email,
    bool? emailVerified,
    bool? mfaEnabled,
    DateTime? lastLoginAt,
    String? lastLoginIp,
    int? dataRetentionDays,
  }) {
    return UserProfile(
      id: id,
      name: name ?? this.name,
      email: email ?? this.email,
      createdAt: createdAt,
      emailVerified: emailVerified ?? this.emailVerified,
      mfaEnabled: mfaEnabled ?? this.mfaEnabled,
      role: role,
      lastLoginAt: lastLoginAt ?? this.lastLoginAt,
      lastLoginIp: lastLoginIp ?? this.lastLoginIp,
      dataRetentionDays: dataRetentionDays ?? this.dataRetentionDays,
    );
  }

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: (json['id'] ?? json['_id'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
      emailVerified: json['email_verified'] == true,
      mfaEnabled: json['mfa_enabled'] == true,
      role: (json['role'] ?? 'user').toString(),
      lastLoginAt: json['last_login_at'] != null
          ? DateTime.tryParse(json['last_login_at'].toString())
          : null,
      lastLoginIp: json['last_login_ip']?.toString(),
      dataRetentionDays: (json['data_retention_days'] is num)
          ? (json['data_retention_days'] as num).toInt()
          : 180,
    );
  }
}
