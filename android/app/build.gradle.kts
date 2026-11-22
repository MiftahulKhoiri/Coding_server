import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Nomor versi dari CI (GITHUB_RUN_NUMBER) agar setiap APK baru bisa memperbarui yang lama.
val ciBuildNumber = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

// Kunci rilis dari environment (secret CI). Bila tidak ada, build rilis hanya boleh memakai
// kunci debug bila diizinkan eksplisit: -Pcodingserver.allowDebugSigning (lihat android/README.md).
val allowDebugSigning = providers.gradleProperty("codingserver.allowDebugSigning").isPresent
val releaseSigning = Properties().apply {
    val path = System.getenv("ANDROID_KEYSTORE_PATH")
    if (path != null && file(path).exists()) {
        setProperty("storeFile", path)
        setProperty("storePassword", System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: "")
        setProperty("keyAlias", System.getenv("ANDROID_KEY_ALIAS") ?: "")
        setProperty("keyPassword", System.getenv("ANDROID_KEY_PASSWORD") ?: "")
    }
}

// Build lokal di Raspberry Pi (ARM64): aapt2 Debian belum bisa membaca android.jar API 35,
// jadi pemeriksaan lokal memakai API 34 (-Pcodingserver.localArm64). APK resmi dibuat CI (API 35).
val localArm64 = providers.gradleProperty("codingserver.localArm64").isPresent

android {
    namespace = "id.codingserver.android"
    compileSdk = if (localArm64) 34 else 35

    defaultConfig {
        applicationId = "id.codingserver.android"
        minSdk = 26
        targetSdk = 35
        versionCode = ciBuildNumber
        versionName = "1.0.$ciBuildNumber"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        getByName("debug") {
            storeFile = rootProject.file("signing/debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
        if (releaseSigning.containsKey("storeFile")) {
            create("release") {
                storeFile = file(releaseSigning.getProperty("storeFile"))
                storePassword = releaseSigning.getProperty("storePassword")
                keyAlias = releaseSigning.getProperty("keyAlias")
                keyPassword = releaseSigning.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = when {
                releaseSigning.containsKey("storeFile") -> signingConfigs.getByName("release")
                allowDebugSigning -> signingConfigs.getByName("debug")
                else -> null
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.all {
            // Tes integrasi dengan backend asli hanya berjalan bila CS_SERVER_URL diisi (di CI).
            it.environment("CS_SERVER_URL", System.getenv("CS_SERVER_URL") ?: "")
            it.environment("CS_ADMIN_PASSWORD", System.getenv("CS_ADMIN_PASSWORD") ?: "")
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.splashscreen)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.security.crypto)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.webkit)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.okhttp)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
}

gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { it.project == project && it.name.matches(Regex("(assemble|bundle|package)Release")) }
    if (wantsRelease && !releaseSigning.containsKey("storeFile") && !allowDebugSigning) {
        throw GradleException(
            "Kunci rilis tidak ditemukan. Set ANDROID_KEYSTORE_PATH/ANDROID_KEYSTORE_PASSWORD/ANDROID_KEY_ALIAS/" +
                "ANDROID_KEY_PASSWORD, atau untuk uji lokal tambahkan -Pcodingserver.allowDebugSigning."
        )
    }
}

// CodeMirror/xterm assets are generated from web_editor. A clean checkout may not
// contain android/app/src/main/assets/web/*.html, which leaves the Android WebView blank.
// Rebuild if files are absent OR empty/truncated (an empty editor.html was found in main).
val webEditorDir = rootProject.projectDir.parentFile.resolve("web_editor")
val webEditorAssets = projectDir.resolve("src/main/assets/web")
val buildWebEditorAssets = tasks.register("buildWebEditorAssets") {
    doLast {
        val editorHtml = webEditorAssets.resolve("editor.html")
        val terminalHtml = webEditorAssets.resolve("terminal.html")
        // Generated CodeMirror/xterm HTML includes large self-contained JS bundles.
        // Empty or tiny files are not valid editor assets even if they exist.
        if (!editorHtml.isFile || editorHtml.length() < 10_000 ||
            !terminalHtml.isFile || terminalHtml.length() < 10_000) {
            if (!webEditorDir.resolve("node_modules/esbuild").exists()) {
                exec {
                    workingDir(webEditorDir)
                    commandLine("npm", "ci", "--no-audit", "--no-fund")
                }
            }
            exec {
                workingDir(webEditorDir)
                commandLine("npm", "run", "build")
            }
        }
        if (!editorHtml.isFile || editorHtml.length() < 10_000 ||
            !terminalHtml.isFile || terminalHtml.length() < 10_000) {
            throw GradleException("Aset WebView editor/terminal tidak lengkap atau kosong: ${webEditorAssets.absolutePath}")
        }
    }
}
tasks.named("preBuild").configure { dependsOn(buildWebEditorAssets) }

if (localArm64) {
    tasks.matching { it.name.startsWith("check") && it.name.endsWith("AarMetadata") }.configureEach { enabled = false }
}
