import java.io.FileInputStream
import java.util.Base64
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val hasReleaseKeystore = keystorePropertiesFile.exists().also { exists ->
    if (exists) {
        FileInputStream(keystorePropertiesFile).use { keystoreProperties.load(it) }
    }
}

android {
    namespace = "com.jobmail.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.jobmail.app"
        minSdk = flutter.minSdkVersion.coerceAtLeast(24)
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        debug {
            manifestPlaceholders["networkSecurityConfig"] = "@xml/network_security_config_dev"
        }
        release {
            val allowLocalHttpFromDartDefines =
                (project.findProperty("dart-defines")?.toString() ?: "")
                    .split(",")
                    .filter { it.isNotBlank() }
                    .any { encoded ->
                        val decoded = runCatching {
                            String(Base64.getDecoder().decode(encoded), Charsets.UTF_8)
                        }.getOrNull()
                        decoded == "JOBMAIL_ALLOW_LOCAL_HTTP=true"
                    }
            val allowLocalHttp =
                allowLocalHttpFromDartDefines ||
                    project.findProperty("jobmailAllowLocalHttp")?.toString()?.toBoolean() == true
            manifestPlaceholders["networkSecurityConfig"] = if (allowLocalHttp) {
                "@xml/network_security_config_dev"
            } else {
                "@xml/network_security_config"
            }
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = if (hasReleaseKeystore) {
                signingConfigs.getByName("release")
            } else {
                // Preserves debug signing fallback so `flutter build apk --release` works
                // prior to configuring an upload keystore in android/key.properties.
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
