package com.sepsis.watch

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.samsung.android.service.health.tracking.ConnectionListener
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import java.util.concurrent.Executors

/**
 * One ECG + PPG check for pulse arrival time (about 30 s, finger on the top button).
 *
 * The Samsung ECG tracker returns both signals in the same packets: each packet is 10 rows that share
 * one timestamp (10 ECG samples 2 ms apart; the green PPG value sits on rows 0 and 5, so 100 Hz; the
 * lead-off flag is on row 0). Packets are posted to the board's /api/ecg once a second, which does the
 * analysis. Needs the READ_ADDITIONAL_HEALTH_DATA permission granted (`adb shell pm grant`) and the
 * app in the foreground. Start it with [start].
 */
object EcgCheck {
    private const val CHECK_MS = 35_000L
    private const val PACKETS_PER_POST = 50

    @Volatile var status = "ECG: idle"
        private set

    private val main = Handler(Looper.getMainLooper())
    private val net = Executors.newSingleThreadExecutor()
    private var running = false

    fun start(context: Context) {
        main.post {
            if (running) return@post
            running = true
            status = "ECG: connecting"
            val app = context.applicationContext
            val uplink = Uplink(app).also { it.start() }
            val url = Settings(app).url().replace("/vitals", "/api/ecg")
            var service: HealthTrackingService? = null
            var tracker: HealthTracker? = null

            fun finish(message: String) {
                main.post {
                    try { tracker?.unsetEventListener() } catch (_: Throwable) {}
                    try { service?.disconnectService() } catch (_: Throwable) {}
                    uplink.stop()
                    running = false
                    status = message
                }
            }

            val pt = ArrayList<Long>()
            val ecg = ArrayList<Float>()
            val ppg = ArrayList<Int>()
            val lead = ArrayList<Int>()
            val packet = ArrayList<DataPoint>()

            fun flush() {
                if (pt.isEmpty()) return
                val body = StringBuilder("{\"pt\":").append(pt).append(",\"ecg\":").append(ecg)
                    .append(",\"ppg\":").append(ppg).append(",\"lead\":").append(lead).append("}").toString()
                pt.clear(); ecg.clear(); ppg.clear(); lead.clear()
                net.execute { uplink.postOnce(url, body) }
            }

            val listener = object : HealthTracker.TrackerEventListener {
                override fun onDataReceived(list: MutableList<DataPoint>) {
                    for (dp in list) {
                        packet.add(dp)
                        if (packet.size < 10) continue
                        val first = packet[0]
                        pt.add(first.timestamp)
                        lead.add(first.getValue(ValueKey.EcgSet.LEAD_OFF) ?: 5)
                        for (r in packet) ecg.add(r.getValue(ValueKey.EcgSet.ECG_MV) ?: 0f)
                        ppg.add(packet[0].getValue(ValueKey.EcgSet.PPG_GREEN) ?: -1)
                        ppg.add(packet[5].getValue(ValueKey.EcgSet.PPG_GREEN) ?: -1)
                        packet.clear()
                        if (pt.size >= PACKETS_PER_POST) flush()
                    }
                    status = "ECG: recording"
                }

                override fun onFlushCompleted() {}

                override fun onError(error: HealthTracker.TrackerError) {
                    finish("ECG error: $error")
                }
            }

            val connection = object : ConnectionListener {
                override fun onConnectionSuccess() {
                    main.post {
                        try {
                            tracker = service?.getHealthTracker(HealthTrackerType.ECG_ON_DEMAND)?.also {
                                it.setEventListener(listener)
                            }
                            status = "ECG: put a finger on the top button"
                            main.postDelayed({ flush(); finish("ECG: done") }, CHECK_MS)
                        } catch (t: Throwable) {
                            finish("ECG could not start: ${t.message ?: t.javaClass.simpleName}")
                        }
                    }
                }

                override fun onConnectionEnded() {}

                override fun onConnectionFailed(e: HealthTrackerException) {
                    finish("ECG connection failed (code ${e.errorCode})")
                }
            }

            try {
                service = HealthTrackingService(connection, app).also { it.connectService() }
            } catch (t: Throwable) {
                finish("ECG could not connect: ${t.message ?: t.javaClass.simpleName}")
            }
        }
    }
}
