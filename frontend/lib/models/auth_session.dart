import 'user_profile.dart';

/// Authenticated session payload (supports rotating refresh tokens and MFA login challenges).
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.user,
    this.refreshToken,
    this.sessionId,
    this.mfaRequired = false,
    this.mfaChallengeToken,
  });

  final String accessToken;
  final String? refreshToken;
  final String? sessionId;
  final bool mfaRequired;
  final String? mfaChallengeToken;
  final UserProfile user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: (json['access_token'] ?? '').toString(),
      refreshToken: json['refresh_token']?.toString(),
      sessionId: json['session_id']?.toString(),
      mfaRequired: json['mfa_required'] == true,
      mfaChallengeToken: json['mfa_challenge_token']?.toString(),
      user: UserProfile.fromJson(
        (json['user'] as Map<String, dynamic>?) ?? <String, dynamic>{},
      ),
    );
  }
}
