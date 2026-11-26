import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

enum AccountSyncStatus {
  synced,
  syncing,
  pending,
  error,
  revoked;

  String get label {
    switch (this) {
      case AccountSyncStatus.synced:
        return 'Synced';
      case AccountSyncStatus.syncing:
        return 'Syncing';
      case AccountSyncStatus.pending:
        return 'Pending';
      case AccountSyncStatus.error:
        return 'Sync Error';
      case AccountSyncStatus.revoked:
        return 'Access Revoked';
    }
  }

  Color get color {
    switch (this) {
      case AccountSyncStatus.synced:
        return AppColors.success;
      case AccountSyncStatus.syncing:
        return AppColors.info;
      case AccountSyncStatus.pending:
        return AppColors.accentAmber;
      case AccountSyncStatus.error:
      case AccountSyncStatus.revoked:
        return AppColors.error;
    }
  }

  static AccountSyncStatus fromApi(String? raw) {
    switch (raw?.trim().toUpperCase()) {
      case 'SYNCED':
        return AccountSyncStatus.synced;
      case 'SYNCING':
        return AccountSyncStatus.syncing;
      case 'ERROR':
        return AccountSyncStatus.error;
      case 'REVOKED':
        return AccountSyncStatus.revoked;
      default:
        return AccountSyncStatus.pending;
    }
  }
}

/// Represents a connected Gmail account authorized via OAuth 2.0 (read-only).
class ConnectedAccount {
  const ConnectedAccount({
    required this.id,
    required this.emailAddress,
    required this.provider,
    required this.connectedAt,
    required this.syncStatus,
    this.lastSyncedAt,
    this.statusMessage,
  });

  final String id;
  final String emailAddress;
  final String provider;
  final DateTime connectedAt;
  final DateTime? lastSyncedAt;
  final AccountSyncStatus syncStatus;
  final String? statusMessage;

  ConnectedAccount copyWith({
    AccountSyncStatus? syncStatus,
    DateTime? lastSyncedAt,
    String? statusMessage,
  }) {
    return ConnectedAccount(
      id: id,
      emailAddress: emailAddress,
      provider: provider,
      connectedAt: connectedAt,
      lastSyncedAt: lastSyncedAt ?? this.lastSyncedAt,
      syncStatus: syncStatus ?? this.syncStatus,
      statusMessage: statusMessage ?? this.statusMessage,
    );
  }

  factory ConnectedAccount.fromJson(Map<String, dynamic> json) {
    return ConnectedAccount(
      id: (json['id'] ?? json['_id'] ?? '').toString(),
      emailAddress: (json['email_address'] ?? '').toString(),
      provider: (json['provider'] ?? 'google').toString(),
      connectedAt: DateTime.tryParse((json['connected_at'] ?? '').toString()) ??
          DateTime.now(),
      lastSyncedAt: json['last_synced_at'] != null
          ? DateTime.tryParse(json['last_synced_at'].toString())
          : null,
      syncStatus: AccountSyncStatus.fromApi(json['sync_status']?.toString()),
      statusMessage: json['status_message']?.toString(),
    );
  }
}
