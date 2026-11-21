package com.sepsis.watch

import java.util.Locale

/** How long a reading counts as current. Older readings are sent as null, never repeated forever. */
object MaxAge {
    const val HR_MS = 15_000L          // HR arrives about once a second while the sensor is working
    const val SKIN_TEMP_MS = 5 * 60_000L
    const val SPO2_MS = 10 * 60_000L   // SpO2 is a ~30 s on-demand spot measurement
}

/** Latest value of one vital and when it arrived (wall-clock ms). Written by sensor callbacks, read by the send tick. */
class Reading {
    @Volatile private var latest: Pair<Double, Long>? = null

    fun set(value: Double, atMs: Long = System.currentTimeMillis()) {
        latest = value to atMs
    }

    /** The value if it arrived within [maxAgeMs] of [nowMs], otherwise null. */
    fun fresh(nowMs: Long, maxAgeMs: Long): Double? = freshWithTime(nowMs, maxAgeMs)?.first

    /** Value and the time it was taken, if it arrived within [maxAgeMs] of [nowMs]. */
    fun freshWithTime(nowMs: Long, maxAgeMs: Long): Pair<Double, Long>? =
        latest?.takeIf { nowMs - it.second <= maxAgeMs }
}

/**
 * One sample in the board's JSON contract. Null means "not measured", never a placeholder.
 * `hr` and `skin_temp_c` are current at `t`; `spo2` is a spot measurement taken at `spo2_t`.
 */
data class Snapshot(
    val t: Long,
    val hr: Int?,
    val spo2: Int?,
    val spo2T: Long?,
    val skinTempC: Double?,
) {
    // Built by hand: org.json writes 34.0 as `34`, and the contract says skin_temp_c is a float.
    // Every value is a number or null, so nothing needs escaping.
    fun toJson(): String {
        val skin = skinTempC?.takeIf { it.isFinite() }?.let { String.format(Locale.US, "%.2f", it) } ?: "null"
        // spo2_t is null exactly when spo2 is null.
        val spo2Time = spo2T?.takeIf { spo2 != null }
        return """{"t":$t,"hr":${hr ?: "null"},"spo2":${spo2 ?: "null"},"spo2_t":${spo2Time ?: "null"},""" +
            """"skin_temp_c":$skin,"source":"watch"}"""
    }
}

/** Where readings come from. The `fake` and `real` flavors each provide a `Sources.create()`. */
interface VitalsSource {
    fun start()
    fun stop()

    /** Called on every send tick (every 5 s), before [snapshot]. */
    fun tick() {}

    fun snapshot(nowMs: Long): Snapshot

    /** Starts a one-off SpO2 measurement. Returns a short message for the screen. */
    fun measureSpo2(): String

    /** A few lines saying where each vital comes from, or why it is missing. */
    fun notes(): String
}
