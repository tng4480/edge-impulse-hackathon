package com.sepsis.watch

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Foreground service: samples vitals and POSTs one sample every 5 s, screen on or off.
 * A partial wake lock keeps the CPU (and so the 5 s timer) running when the screen is off.
 */
class VitalsService : Service() {
    private lateinit var source: VitalsSource
    private lateinit var uplink: Uplink
    private lateinit var settings: Settings
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private val net = Executors.newSingleThreadExecutor()
    private val draining = AtomicBoolean(false)
    private var wakeLock: PowerManager.WakeLock? = null

    private val tick = object : Runnable {
        override fun run() {
            sendTick()
            handler.postDelayed(this, PERIOD_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        source = Sources.create(this)
        uplink = Uplink(this)
        settings = Settings(this)
        thread = HandlerThread("vitals").apply { start() }
        handler = Handler(thread.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_SPO2 -> {
                LiveState.message = if (LiveState.running) source.measureSpo2() else "Press Start first"
                if (!LiveState.running) stopSelf()
                return START_NOT_STICKY
            }
            else -> startSampling()
        }
        return START_STICKY
    }

    private fun startSampling() {
        if (LiveState.running) return
        try {
            val notification = buildNotification()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (e: RuntimeException) {
            // e.g. SecurityException when no health permission was granted.
            LiveState.lastError = "Could not start foreground service: ${e.message}"
            stopSelf()
            return
        }
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "SepsisWatch:sampling")
            .apply { acquire() }
        uplink.start()
        source.start()
        LiveState.running = true
        LiveState.lastError = null
        handler.postDelayed(tick, 1_000) // first sample after sensors have had a moment
    }

    private fun sendTick() {
        source.tick()
        val snapshot = source.snapshot(System.currentTimeMillis())
        LiveState.lastSnapshot = snapshot
        LiveState.notes = source.notes()
        uplink.enqueue(snapshot.toJson())
        LiveState.queued = uplink.queued()

        val url = settings.url() // read every tick so an address change applies straight away
        if (draining.compareAndSet(false, true)) {
            net.execute {
                try {
                    uplink.drain(url)
                } finally {
                    LiveState.queued = uplink.queued()
                    draining.set(false)
                }
            }
        }
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        if (LiveState.running) {
            source.stop()
            uplink.stop()
        }
        wakeLock?.let { if (it.isHeld) it.release() }
        net.shutdownNow()
        thread.quitSafely()
        LiveState.running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(): android.app.Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Vitals streaming", NotificationManager.IMPORTANCE_LOW)
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Sending vitals to the board every 5 s")
            .setContentIntent(open)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    companion object {
        const val PERIOD_MS = 5_000L
        const val ACTION_START = "com.sepsis.watch.START"
        const val ACTION_STOP = "com.sepsis.watch.STOP"
        const val ACTION_SPO2 = "com.sepsis.watch.SPO2"
        private const val CHANNEL_ID = "vitals"
        private const val NOTIFICATION_ID = 1

        fun intent(context: Context, action: String) =
            Intent(context, VitalsService::class.java).setAction(action)
    }
}
