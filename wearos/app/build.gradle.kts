plugins {
    id("com.android.application")
}

// The Samsung Health Sensor SDK .aar can't be committed (licence) and needs a Samsung login to
// download, so the build adapts: with the .aar present it compiles the real Samsung source, without
// it a stub that reports the SDK as missing (skin temp and SpO2 then go out as null).
val samsungAars = file("libs").listFiles { f -> f.name.endsWith(".aar") }?.toList().orEmpty()
val hasSamsungSdk = samsungAars.isNotEmpty()
logger.lifecycle("Samsung Health Sensor SDK: " + if (hasSamsungSdk) samsungAars.joinToString { it.name } else "not found in app/libs (HR only)")

android {
    namespace = "com.sepsis.watch"
    compileSdk = 37 // androidx.core 1.19 needs it; targetSdk stays 36 (the watch runs Wear OS 6 = API 36)

    defaultConfig {
        applicationId = "com.sepsis.watch"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        buildConfigField("boolean", "HAS_SAMSUNG_SDK", hasSamsungSdk.toString())
    }

    flavorDimensions += "data"
    productFlavors {
        // Constant fake vitals, for the emulator and for testing the board link. Never install on a patient.
        create("fake") {
            dimension = "data"
            applicationIdSuffix = ".fake"
            versionNameSuffix = "-fake"
        }
        // Real sensors only; anything unreadable is sent as null.
        create("real") {
            dimension = "data"
        }
    }

    sourceSets {
        getByName("main") {
            kotlin.directories.add(if (hasSamsungSdk) "src/samsung/java" else "src/nosamsung/java")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the debug key so the release APK installs with adb without a keystore.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core:1.19.1")
    if (hasSamsungSdk) {
        implementation(files(samsungAars))
    }
}
