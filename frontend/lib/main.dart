import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'app.dart';
import 'services/api_client.dart';
import 'services/api_jobmail_repository.dart';
import 'services/preferences_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final sharedPreferences = await SharedPreferences.getInstance();
  final preferencesService = PreferencesService(sharedPreferences);
  await preferencesService.initSecureSession();
  final apiClient = ApiClient(baseUrl: preferencesService.apiBaseUrl);
  final repository = ApiJobMailRepository(apiClient);

  runApp(
    JobMailApp(
      repository: repository,
      preferencesService: preferencesService,
      apiClient: apiClient,
    ),
  );
}
