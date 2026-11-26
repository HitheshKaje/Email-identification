/// Authenticated JobMail user profile.
class UserProfile {
  const UserProfile({
    required this.id,
    required this.name,
    required this.email,
    this.createdAt,
  });

  final String id;
  final String name;
  final String email;
  final DateTime? createdAt;

  UserProfile copyWith({
    String? name,
    String? email,
  }) {
    return UserProfile(
      id: id,
      name: name ?? this.name,
      email: email ?? this.email,
      createdAt: createdAt,
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
    );
  }
}
