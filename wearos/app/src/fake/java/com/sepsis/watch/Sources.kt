package com.sepsis.watch

import android.content.Context

/** `fake` flavor: constant values, to test the board link without sensors (e.g. on the emulator). */
object Sources {
    fun create(context: Context): VitalsSource = FakeSource
}

private object FakeSource : VitalsSource {
    override fun start() {}
    override fun stop() {}
    // spo2_t 2 minutes before t, so the board can exercise its "reading age" handling.
    // 6 IBIs of 833 ms is what a constant 72 bpm produces in 5 s.
    override fun snapshot(nowMs: Long) = Snapshot(
        t = nowMs, hr = 72, spo2 = 98, spo2T = nowMs - 120_000, skinTempC = 34.0,
        ambientC = 22.0, ibiMs = List(6) { 833 },
    )
    override fun measureSpo2() = "Fake build: SpO2 is a constant 98"
    override fun notes() = "FAKE constants: HR 72, SpO2 98, skin 34.0 °C"
}
