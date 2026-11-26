import 'package:flutter/foundation.dart';
import '../models/notification_item.dart';
import '../models/notification_preferences.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';
import '../services/preferences_service.dart';

/// State provider for job notifications feed and alert preferences.
class NotificationsProvider extends ChangeNotifier {
  NotificationsProvider(this._repository, this._prefsService)
      : _preferences = _prefsService.notificationPreferences;

  final JobMailRepository _repository;
  final PreferencesService _prefsService;

  List<NotificationItem> _notifications = const <NotificationItem>[];
  NotificationPreferences _preferences;
  bool _isLoading = false;
  bool _isSavingPreferences = false;
  String? _errorMessage;

  List<NotificationItem> get notifications => _notifications;
  NotificationPreferences get preferences => _preferences;
  bool get isLoading => _isLoading;
  bool get isSavingPreferences => _isSavingPreferences;
  String? get errorMessage => _errorMessage;

  int get unreadCount => _notifications.where((n) => !n.isRead).length;

  Future<void> loadNotifications() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final results = await Future.wait<dynamic>(<Future<dynamic>>[
        _repository.getNotifications(),
        _repository.getNotificationPreferences(),
      ]);
      _notifications = results[0] as List<NotificationItem>;
      _preferences = results[1] as NotificationPreferences;
      await _prefsService.setNotificationPreferences(_preferences);
    } on ApiException catch (e) {
      _errorMessage = e.message;
    } catch (_) {
      _errorMessage = 'Unable to load notifications.';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> markAsRead(String notificationId) async {
    final idx = _notifications.indexWhere((n) => n.id == notificationId);
    if (idx != -1 && !_notifications[idx].isRead) {
      final updated = List<NotificationItem>.from(_notifications);
      updated[idx] = updated[idx].copyWith(isRead: true);
      _notifications = updated;
      notifyListeners();
    }
    try {
      await _repository.markNotificationRead(notificationId);
    } catch (_) {
      // Keep UI responsive; backend sync will reconcile if temporarily offline.
    }
  }

  Future<bool> updatePreferences(NotificationPreferences nextPrefs) async {
    _preferences = nextPrefs;
    await _prefsService.setNotificationPreferences(nextPrefs);
    _isSavingPreferences = true;
    notifyListeners();

    try {
      _preferences =
          await _repository.updateNotificationPreferences(nextPrefs);
      await _prefsService.setNotificationPreferences(_preferences);
      return true;
    } on ApiException catch (e) {
      _errorMessage = e.message;
      return false;
    } catch (_) {
      _errorMessage = 'Saved locally; backend preference update failed.';
      return false;
    } finally {
      _isSavingPreferences = false;
      notifyListeners();
    }
  }
}
