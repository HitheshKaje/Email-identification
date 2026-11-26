import 'package:flutter/foundation.dart';
import '../models/dashboard_stats.dart';
import '../models/email_item.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';

/// State provider for the Dashboard statistics and recent job-related emails.
class DashboardProvider extends ChangeNotifier {
  DashboardProvider(this._repository);

  final JobMailRepository _repository;

  DashboardStats _stats = const DashboardStats();
  List<EmailItem> _recentEmails = const <EmailItem>[];
  bool _isLoading = false;
  bool _isSyncing = false;
  String? _errorMessage;

  DashboardStats get stats => _stats;
  List<EmailItem> get recentEmails => _recentEmails;
  bool get isLoading => _isLoading;
  bool get isSyncing => _isSyncing;
  String? get errorMessage => _errorMessage;

  Future<void> loadDashboard() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final results = await Future.wait<dynamic>(<Future<dynamic>>[
        _repository.getDashboardStatistics(),
        _repository.getRecentEmails(limit: 8),
      ]);
      _stats = results[0] as DashboardStats;
      _recentEmails = results[1] as List<EmailItem>;
    } on ApiException catch (e) {
      _errorMessage = e.message;
    } catch (_) {
      _errorMessage = 'Failed to load dashboard data.';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> syncNow() async {
    _isSyncing = true;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repository.triggerSync();
      await loadDashboard();
      return true;
    } on ApiException catch (e) {
      _errorMessage = e.message;
      return false;
    } catch (_) {
      _errorMessage = 'Failed to synchronize Gmail accounts.';
      return false;
    } finally {
      _isSyncing = false;
      notifyListeners();
    }
  }

  void applyLocalEmailUpdate(EmailItem updated) {
    final index = _recentEmails.indexWhere((item) => item.id == updated.id);
    if (index != -1) {
      final mutable = List<EmailItem>.from(_recentEmails);
      mutable[index] = updated;
      _recentEmails = mutable;
      notifyListeners();
    }
  }
}
