package com.sepsis.watch

import android.content.Context
import android.os.Handler
import android.os.Looper
import kotlin.math.roundToInt

/** `real` flavor: actual sensors only. Anything not measured recently goes out as null. */
object Sources {
    fun create(context: Context): VitalsSource = RealSource(context.applicationContext)
}

private class RealSource(context: Context) : VitalsSource {
    private val main = Handler(Looper.getMainLooper())
    private val androidHr = AndroidHeartRate(context)
    private val samsung = SamsungSensors(context)

    override fun start() {
        androidHr.start(main)
        samsung.start()
    }

    override fun stop() {
        androidHr.stop()
        samsung.stop()
    }

    override fun tick() = samsung.tick()

    override fun snapshot(nowMs: Long): Snapshot {
        // Prefer Samsung's continuous tracker (it reports wear/motion status); fall back to the Android sensor.
        val hr = samsung.hr.fresh(nowMs, MaxAge.HR_MS) ?: androidHr.reading.fresh(nowMs, MaxAge.HR_MS)
        val spo2 = samsung.spo2.freshWithTime(nowMs, MaxAge.SPO2_MS)
        return Snapshot(
            t = nowMs,
            hr = hr?.roundToInt(),
            spo2 = spo2?.first?.roundToInt(),
            spo2T = spo2?.second,
            skinTempC = samsung.skin.fresh(nowMs, MaxAge.SKIN_TEMP_MS),
        )
    }

    override fun measureSpo2() = samsung.measureSpo2()

    override fun notes() =
        "HR: ${samsung.hrStatus}; ${androidHr.status}\nSkin: ${samsung.skinStatus}\nSpO2: ${samsung.spo2Status}"
}
