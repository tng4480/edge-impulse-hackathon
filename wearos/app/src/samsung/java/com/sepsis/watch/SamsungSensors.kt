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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Samsung Health Sensor SDK trackers (Galaxy Watch only; does not run on the emulator).
 *
 * - Heart rate: HEART_RATE_CONTINUOUS. HEART_RATE_STATUS == 1 means a valid reading.
 * - Skin temperature: SKIN_TEMPERATURE_CONTINUOUS if the watch offers it, otherwise
 *   SKIN_TEMPERATURE_ON_DEMAND once a minute. STATUS == 0 means valid; value is in °C.
 * - SpO2: SPO2_ON_DEMAND only (~30 s, wearer must keep still). STATUS == 2 means complete.
 *
 * Only one on-demand tracker may run at a time, for at most ~30 s, and only while the app is in
 * the foreground. Unregistered apps need Health Platform developer mode, else SDK_POLICY_ERROR.
 * All SDK calls are made on the main thread, so the callbacks arrive there too.
 */
class SamsungSensors(context: Context) {
    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())

    val hr = Reading()
    val spo2 = Reading()
    val skin = Reading()

    @Volatile var hrStatus = "Samsung: not started"
        private set
    @Volatile var skinStatus = "Samsung: not started"
        private set
    @Volatile var spo2Status = "Samsung: not started"
        private set

    private var service: HealthTrackingService? = null
    private var connected = false
    private var supported: List<HealthTrackerType> = emptyList()
    private var hrTracker: HealthTracker? = null
    private var skinContinuous: HealthTracker? = null
    private var skinOnDemandMode = false
    private var lastSkinOnDemandMs = 0L

    /** The on-demand tracker currently running, if any. */
    private var onDemand: HealthTracker? = null
    private var onDemandKind: String? = null
    private val onDemandTimeout = Runnable {
        when (onDemandKind) {
            KIND_SPO2 -> spo2Status = "timed out; keep still, arm on a table, and retry"
            KIND_SKIN -> skinStatus = "on-demand reading timed out"
        }
        finishOnDemand()
    }

    fun start() {
        main.post {
            try {
                setAll("Samsung: connecting")
                service = HealthTrackingService(connectionListener, appContext).also { it.connectService() }
            } catch (t: Throwable) {
                setAll("Samsung SDK failed to start: ${t.message ?: t.javaClass.simpleName}")
            }
        }
    }

    fun stop() {
        main.post {
            finishOnDemand()
            safely { hrTracker?.unsetEventListener() }
            safely { skinContinuous?.unsetEventListener() }
            hrTracker = null
            skinContinuous = null
            safely { service?.disconnectService() }
            service = null
            connected = false
        }
    }

    /** Every 5 s: flush batched continuous data (batched while the screen is off), maybe take a skin reading. */
    fun tick() {
        main.post {
            if (!connected) return@post
            safely { hrTracker?.flush() }
            safely { skinContinuous?.flush() }
            val now = System.currentTimeMillis()
            if (skinOnDemandMode && onDemand == null && now - lastSkinOnDemandMs >= SKIN_ON_DEMAND_EVERY_MS) {
                lastSkinOnDemandMs = now
                startOnDemand(HealthTrackerType.SKIN_TEMPERATURE_ON_DEMAND, KIND_SKIN, skinListener(onDemand = true), 20_000)
            }
        }
    }

    fun measureSpo2(): String {
        if (!connected) return "Samsung service not connected ($spo2Status)"
        if (HealthTrackerType.SPO2_ON_DEMAND !in supported) return "This watch doesn't offer SpO2 to apps"
        main.post {
            if (onDemandKind == KIND_SKIN) finishOnDemand() // SpO2 takes priority over a routine skin reading
            if (onDemand != null) return@post
            spo2Status = "measuring… keep still, arm on a table"
            startOnDemand(HealthTrackerType.SPO2_ON_DEMAND, KIND_SPO2, spo2Listener, 45_000)
        }
        return "Measuring SpO2 (~30 s). Keep still."
    }

    // --- Connection ----------------------------------------------------------------------------

    private val connectionListener = object : ConnectionListener {
        override fun onConnectionSuccess() {
            main.post { onConnected() }
        }

        override fun onConnectionEnded() {
            connected = false
            setAll("Samsung service disconnected")
        }

        override fun onConnectionFailed(e: HealthTrackerException) {
            connected = false
            setAll(
                when (e.errorCode) {
                    HealthTrackerException.OLD_PLATFORM_VERSION -> "Health Platform too old: update it in Galaxy Store"
                    HealthTrackerException.PACKAGE_NOT_INSTALLED -> "Health Platform not installed on this watch"
                    else -> "Samsung connect failed: ${e.message} (code ${e.errorCode})"
                }
            )
        }
    }

    private fun onConnected() {
        val s = service ?: return
        connected = true
        supported = try {
            s.trackingCapability.supportHealthTrackerTypes
        } catch (t: Throwable) {
            setAll("Samsung capability query failed: ${t.message}")
            return
        }

        hrStatus = if (HealthTrackerType.HEART_RATE_CONTINUOUS in supported) {
            hrTracker = track(s, HealthTrackerType.HEART_RATE_CONTINUOUS, hrListener)
            if (hrTracker != null) "Samsung HR starting" else "Samsung HR tracker failed"
        } else {
            "Samsung HR tracker not offered"
        }

        skinStatus = when {
            HealthTrackerType.SKIN_TEMPERATURE_CONTINUOUS in supported -> {
                skinContinuous = track(s, HealthTrackerType.SKIN_TEMPERATURE_CONTINUOUS, skinListener(onDemand = false))
                if (skinContinuous != null) "Samsung continuous, waiting" else "Samsung skin tracker failed"
            }
            HealthTrackerType.SKIN_TEMPERATURE_ON_DEMAND in supported -> {
                skinOnDemandMode = true
                "Samsung on-demand, once a minute (may fail with the screen off)"
            }
            else -> "not offered by this watch"
        }

        spo2Status = if (HealthTrackerType.SPO2_ON_DEMAND in supported) "tap Measure SpO2 (~30 s)" else "not offered by this watch"
    }

    private fun track(s: HealthTrackingService, type: HealthTrackerType, listener: HealthTracker.TrackerEventListener): HealthTracker? =
        try {
            s.getHealthTracker(type).also { it.setEventListener(listener) }
        } catch (t: Throwable) {
            null
        }

    // --- Listeners -----------------------------------------------------------------------------

    private val hrListener = object : HealthTracker.TrackerEventListener {
        override fun onDataReceived(list: MutableList<DataPoint>) {
            for (dp in list) {
                val status = dp.getValue(ValueKey.HeartRateSet.HEART_RATE_STATUS)
                val bpm = dp.getValue(ValueKey.HeartRateSet.HEART_RATE)
                if (status == 1 && bpm != null && bpm > 0) {
                    hr.set(bpm.toDouble())
                    hrStatus = "Samsung continuous HR"
                } else {
                    hrStatus = "Samsung HR: " + heartRateStatusText(status)
                }
            }
        }

        override fun onFlushCompleted() {}

        override fun onError(error: HealthTracker.TrackerError) {
            hrStatus = "Samsung HR error: " + errorText(error)
        }
    }

    private fun skinListener(onDemand: Boolean) = object : HealthTracker.TrackerEventListener {
        override fun onDataReceived(list: MutableList<DataPoint>) {
            val dp = list.lastOrNull()
            if (dp != null) {
                val status = dp.getValue(ValueKey.SkinTemperatureSet.STATUS)
                val celsius = dp.getValue(ValueKey.SkinTemperatureSet.OBJECT_TEMPERATURE)
                if (status == 0 && celsius != null && !celsius.isNaN()) {
                    skin.set(celsius.toDouble())
                    skinStatus = (if (onDemand) "Samsung on-demand" else "Samsung continuous") + ", last ${clock()}"
                } else {
                    skinStatus = "Samsung skin temp invalid (status $status)"
                }
            }
            if (onDemand) finishOnDemand()
        }

        override fun onFlushCompleted() {}

        override fun onError(error: HealthTracker.TrackerError) {
            skinStatus = "Samsung skin temp error: " + errorText(error)
            if (onDemand) finishOnDemand()
        }
    }

    private val spo2Listener = object : HealthTracker.TrackerEventListener {
        override fun onDataReceived(list: MutableList<DataPoint>) {
            for (dp in list) {
                when (val status = dp.getValue(ValueKey.SpO2Set.STATUS)) {
                    0 -> spo2Status = "measuring… keep still"
                    2 -> {
                        val percent = dp.getValue(ValueKey.SpO2Set.SPO2)
                        if (percent != null && percent > 0) {
                            spo2.set(percent.toDouble())
                            spo2Status = "measured at ${clock()} (sent for 10 min)"
                        } else {
                            spo2Status = "measurement returned no value"
                        }
                        finishOnDemand()
                    }
                    else -> {
                        spo2Status = "failed: " + spo2StatusText(status)
                        finishOnDemand()
                    }
                }
            }
        }

        override fun onFlushCompleted() {}

        override fun onError(error: HealthTracker.TrackerError) {
            spo2Status = "error: " + errorText(error)
            finishOnDemand()
        }
    }

    // --- On-demand helpers -----------------------------------------------------------------------

    private fun startOnDemand(type: HealthTrackerType, kind: String, listener: HealthTracker.TrackerEventListener, timeoutMs: Long) {
        val s = service ?: return
        val tracker = track(s, type, listener)
        if (tracker == null) {
            if (kind == KIND_SPO2) spo2Status = "could not start the SpO2 tracker" else skinStatus = "could not start the skin tracker"
            return
        }
        onDemand = tracker
        onDemandKind = kind
        main.postDelayed(onDemandTimeout, timeoutMs)
    }

    private fun finishOnDemand() {
        main.removeCallbacks(onDemandTimeout)
        val tracker = onDemand
        onDemand = null
        onDemandKind = null
        // Unregistering from inside the tracker's own callback is safer done on the next loop pass.
        if (tracker != null) main.post { safely { tracker.unsetEventListener() } }
    }

    // --- Text helpers -----------------------------------------------------------------------

    private fun setAll(status: String) {
        hrStatus = status
        skinStatus = status
        spo2Status = status
    }

    private inline fun safely(block: () -> Unit) {
        try {
            block()
        } catch (_: Throwable) {
        }
    }

    private fun clock() = SimpleDateFormat("HH:mm", Locale.UK).format(Date())

    private fun heartRateStatusText(status: Int?) = when (status) {
        0 -> "measuring"
        -2 -> "watch moving"
        -3 -> "watch off the wrist"
        -8 -> "weak signal / movement"
        -10 -> "signal too weak / too much movement"
        -99 -> "no data yet"
        -999 -> "another sensor has priority"
        else -> "status $status"
    }

    private fun spo2StatusText(status: Int?) = when (status) {
        -4 -> "watch moved"
        -5 -> "signal quality low"
        -6 -> "timed out"
        else -> "status $status"
    }

    private fun errorText(error: HealthTracker.TrackerError) = when (error) {
        HealthTracker.TrackerError.PERMISSION_ERROR -> "permission not granted"
        HealthTracker.TrackerError.SDK_POLICY_ERROR -> "app not allowed; turn on Health Platform developer mode"
    }

    companion object {
        private const val KIND_SPO2 = "spo2"
        private const val KIND_SKIN = "skin"
        private const val SKIN_ON_DEMAND_EVERY_MS = 60_000L
    }
}
