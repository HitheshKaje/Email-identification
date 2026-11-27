import 'package:flutter/foundation.dart';
import '../models/connected_account.dart';
import '../services/api_exceptions.dart';
import '../services/jobmail_repository.dart';

/// State provider for managing connected Google/Gmail OAuth accounts and syncs.
class AccountsProvider extends ChangeNotifier {
  AccountsProvider(this._repository);

  final JobMailRepository _repository;

  List<ConnectedAccount> _accounts = const <ConnectedAccount>[];
  bool _isLoading = false;
  bool _isConnecting = false;
  String? _syncingAccountId;
  String? _verifyingAccountId;
  String? _errorMessage;
  String? _actionError;
  String? _lastSyncMessage;

  List<ConnectedAccount> get accounts => _accounts;
  bool get isLoading => _isLoading;
  bool get isConnecting => _isConnecting;
  String? get syncingAccountId => _syncingAccountId;
  String? get verifyingAccountId => _verifyingAccountId;
  String? get errorMessage => _errorMessage;
  String? get actionError => _actionError;
  String? get lastSyncMessage => _lastSyncMessage;

  Future<void> loadAccounts() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      _accounts = await _repository.getConnectedAccounts();
    } on ApiException catch (e) {
      _errorMessage = e.message;
    } catch (_) {
      _errorMessage = 'Unable to load connected Gmail accounts.';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<String?> requestGoogleConnectUrl() async {
    _isConnecting = true;
    _actionError = null;
    notifyListeners();

    try {
      return await _repository.initiateGoogleOAuth();
    } on ApiException catch (e) {
      _actionError = e.message;
      return null;
    } catch (_) {
      _actionError = 'Unable to start Google OAuth connection.';
      return null;
    } finally {
      _isConnecting = false;
      notifyListeners();
    }
  }

  Future<bool> syncAccount(String accountId) async {
    _syncingAccountId = accountId;
    _actionError = null;
    _lastSyncMessage = null;
    notifyListeners();

    try {
      _lastSyncMessage = await _repository.triggerSync(accountId: accountId);
      await loadAccounts();
      return true;
    } on ApiException catch (e) {
      _actionError = e.message;
      await loadAccounts();
      return false;
    } catch (_) {
      _actionError = 'Failed to synchronize account.';
      return false;
    } finally {
      _syncingAccountId = null;
      notifyListeners();
    }
  }

  Future<bool> verifyAccount(String accountId) async {
    _verifyingAccountId = accountId;
    _actionError = null;
    notifyListeners();

    try {
      final updated = await _repository.verifyAccount(accountId);
      final idx = _accounts.indexWhere((a) => a.id == updated.id);
      if (idx != -1) {
        final copy = List<ConnectedAccount>.from(_accounts);
        copy[idx] = updated;
        _accounts = copy;
      }
      return true;
    } on ApiException catch (e) {
      _actionError = e.message;
      await loadAccounts();
      return false;
    } catch (_) {
      _actionError = 'Unable to verify Gmail account status.';
      return false;
    } finally {
      _verifyingAccountId = null;
      notifyListeners();
    }
  }

  Future<bool> disconnectAccount(String accountId) async {
    _actionError = null;
    try {
      await _repository.disconnectAccount(accountId);
      _accounts = _accounts.where((a) => a.id != accountId).toList();
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      _actionError = e.message;
      notifyListeners();
      return false;
    } catch (_) {
      _actionError = 'Failed to disconnect Gmail account.';
      notifyListeners();
      return false;
    }
  }
}
