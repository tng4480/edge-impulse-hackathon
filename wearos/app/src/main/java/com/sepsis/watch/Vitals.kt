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
 * `hr`, `skin_temp_c` and `ambient_c` are current at `t`; `spo2` is a spot measurement taken at
 * `spo2_t`; `ibi_ms` holds the valid inter-beat intervals received since the previous sample.
 */
data class Snapshot(
    val t: Long,
    val hr: Int?,
    val spo2: Int?,
    val spo2T: Long?,
    val skinTempC: Double?,
    val ambientC: Double? = null,
    val ibiMs: List<Int>? = null,
) {
    // Built by hand: org.json writes 34.0 as `34`, and the contract wants floats for temperatures.
    // Every value is a number, a list of numbers or null, so nothing needs escaping.
    fun toJson(): String {
        // spo2_t is null exactly when spo2 is null; an empty IBI list is sent as null.
        val spo2Time = spo2T?.takeIf { spo2 != null }
        val ibi = ibiMs?.takeIf { it.isNotEmpty() }?.joinToString(",", "[", "]") ?: "null"
        return """{"t":$t,"hr":${hr ?: "null"},"spo2":${spo2 ?: "null"},"spo2_t":${spo2Time ?: "null"},""" +
            """"skin_temp_c":${celsius(skinTempC)},"ambient_c":${celsius(ambientC)},"ibi_ms":$ibi,"source":"watch"}"""
    }

    private fun celsius(v: Double?) = v?.takeIf { it.isFinite() }?.let { String.format(Locale.US, "%.2f", it) } ?: "null"
}

/** Inter-beat intervals collected between send ticks. Sensor callbacks add, the send tick drains. */
class IbiBuffer {
    private val intervals = ArrayList<Int>()

    @Synchronized
    fun add(ms: Int) {
        if (intervals.size < MAX) intervals.add(ms)
    }

    /** Everything received since the last call (null if nothing). */
    @Synchronized
    fun drain(): List<Int>? = if (intervals.isEmpty()) null else intervals.toList().also { intervals.clear() }

    private companion object {
        const val MAX = 120 // 5 s at up to ~200 bpm with slack, and a guard if ticks stall
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
