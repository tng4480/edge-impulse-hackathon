package com.sepsis.watch

import android.content.Context

/** Stand-in used when the Samsung Health Sensor SDK .aar is not in app/libs: there is no ECG source. */
object EcgCheck {
    @Volatile var status = "ECG needs the Samsung SDK, which isn't in this build"
        private set

    @Suppress("UNUSED_PARAMETER")
    fun start(context: Context) {}
}
