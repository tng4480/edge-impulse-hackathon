package com.sepsis.watch

import android.content.Context

/**
 * Stand-in used when the Samsung Health Sensor SDK .aar is not in app/libs.
 * Skin temperature and SpO2 have no other source on the watch, so they stay null.
 */
@Suppress("UNUSED_PARAMETER")
class SamsungSensors(context: Context) {
    val hr = Reading()
    val spo2 = Reading()
    val skin = Reading()
    val ambient = Reading()
    val ibi = IbiBuffer()

    val hrStatus = "Samsung SDK not in this build"
    val skinStatus = "unavailable (Samsung SDK .aar not in app/libs)"
    val spo2Status = "unavailable (Samsung SDK .aar not in app/libs)"

    fun start() {}
    fun stop() {}
    fun tick() {}
    fun measureSpo2() = "SpO2 needs the Samsung SDK, which isn't in this build"
}
