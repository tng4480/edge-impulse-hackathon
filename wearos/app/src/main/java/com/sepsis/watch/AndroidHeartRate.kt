package com.sepsis.watch

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler

/**
 * Heart rate from the standard Android sensor (TYPE_HEART_RATE). Works on any Wear OS watch and is
 * the fallback when the Samsung SDK isn't in the build or isn't allowed to run.
 */
class AndroidHeartRate(context: Context) : SensorEventListener {
    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val sensor: Sensor? = sensorManager?.getDefaultSensor(Sensor.TYPE_HEART_RATE)
    val reading = Reading()

    @Volatile var status: String = if (sensor == null) "no Android HR sensor" else "Android HR idle"
        private set

    fun start(handler: Handler) {
        val s = sensor ?: return
        val ok = sensorManager.registerListener(this, s, SensorManager.SENSOR_DELAY_NORMAL, handler)
        status = if (ok) "Android HR waiting for signal" else "Android HR refused (permission?)"
    }

    fun stop() {
        sensorManager?.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent) {
        val bpm = event.values.firstOrNull() ?: return
        // Accuracy -1 = no contact, 0 = unreliable: don't report those as a heart rate.
        if (bpm > 0f && event.accuracy >= SensorManager.SENSOR_STATUS_ACCURACY_LOW) {
            reading.set(bpm.toDouble())
            status = "Android HR sensor"
        } else {
            status = "Android HR: no reliable signal (accuracy ${event.accuracy})"
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
