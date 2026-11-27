package com.sepsis.watch

import android.Manifest
import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.LayerDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.accessibility.AccessibilityManager
import android.view.animation.LinearInterpolator
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var settings: Settings
    private lateinit var link: TextView
    private lateinit var linkDetail: TextView
    private lateinit var hr: TextView
    private lateinit var spo2: TextView
    private lateinit var skin: TextView
    private lateinit var notes: TextView
    private lateinit var toggle: Button
    private lateinit var unwell: Button
    private lateinit var checkinStatus: TextView
    private lateinit var ecgStatus: TextView
    private lateinit var host: EditText
    private lateinit var port: EditText

    private val ui = Handler(Looper.getMainLooper())

    // "I feel unwell" is hold to confirm: it sends only after HOLD_MS of pressing, so a brush of the sleeve does nothing.
    private var hold: ValueAnimator? = null
    private var seenCheckinAt = 0L
    private var wasConnected = false
    private var shownRunning: Boolean? = null
    private val refresher = object : Runnable {
        override fun run() {
            refresh()
            ui.postDelayed(this, 1_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = Settings(this)

        link = findViewById(R.id.link)
        linkDetail = findViewById(R.id.linkDetail)
        hr = findViewById(R.id.hr)
        spo2 = findViewById(R.id.spo2)
        skin = findViewById(R.id.skin)
        notes = findViewById(R.id.sensorNotes)
        toggle = findViewById(R.id.toggle)
        unwell = findViewById(R.id.unwell)
        checkinStatus = findViewById(R.id.checkinStatus)
        ecgStatus = findViewById(R.id.ecgStatus)
        host = findViewById(R.id.host)
        port = findViewById(R.id.port)

        findViewById<View>(R.id.fakeBanner).visibility =
            if (BuildConfig.FLAVOR == "fake") View.VISIBLE else View.GONE
        applyAddressExtras(intent)

        toggle.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            if (LiveState.running) {
                startService(VitalsService.intent(this, VitalsService.ACTION_STOP))
            } else {
                requestPermissionsThenStart()
            }
        }
        unwell.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> startHold()
                MotionEvent.ACTION_UP -> { cancelHold(); v.performClick() }
                MotionEvent.ACTION_CANCEL -> cancelHold()
            }
            true
        }
        // A screen-reader user cannot hold, so their double-tap (a click) sends straight away.
        unwell.setOnClickListener {
            if (getSystemService(AccessibilityManager::class.java).isTouchExplorationEnabled) sendCheckin()
        }
        findViewById<Button>(R.id.measureSpo2).setOnClickListener {
            if (LiveState.running) {
                startService(VitalsService.intent(this, VitalsService.ACTION_SPO2))
            } else {
                toast("Start monitoring first")
            }
        }
        // One ECG + PPG check for pulse arrival time. EcgTriggerReceiver starts it; the caption shows EcgCheck.status.
        findViewById<Button>(R.id.ecgCheck).setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendBroadcast(Intent("com.sepsis.ECG_CHECK").setPackage(packageName))
        }
        findViewById<Button>(R.id.save).setOnClickListener { saveAddress() }
        // "Done" on the watch keypad saves straight away.
        val saveOnDone = TextView.OnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                saveAddress()
                true
            } else {
                false
            }
        }
        host.setOnEditorActionListener(saveOnDone)
        port.setOnEditorActionListener(saveOnDone)

        host.clearFocus()
        port.clearFocus()
        findViewById<ScrollView>(R.id.scroll).apply {
            requestFocus()
            post { scrollTo(0, 0) }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        applyAddressExtras(intent)
    }

    /**
     * Typing an IP on a watch is fiddly, so the address can also be set from the laptop:
     * adb shell am start -n com.sepsis.watch/.MainActivity --es host 192.168.1.50 --ei port 8000
     */
    private fun applyAddressExtras(intent: Intent?) {
        intent?.getStringExtra("host")?.trim()?.takeIf { it.isNotEmpty() }?.let { settings.host = it }
        intent?.getIntExtra("port", -1)?.takeIf { it in 1..65535 }?.let { settings.port = it }
        host.setText(settings.host)
        port.setText(settings.port.toString())
    }

    override fun onResume() {
        super.onResume()
        ui.post(refresher)
    }

    override fun onPause() {
        ui.removeCallbacks(refresher)
        super.onPause()
    }

    private fun saveAddress() {
        val h = host.text.toString().trim()
        val p = port.text.toString().trim().toIntOrNull()
        if (h.isEmpty() || p == null || p !in 1..65535) {
            toast("Enter an IP and a port 1-65535")
            return
        }
        settings.host = h
        settings.port = p
        getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(host.windowToken, 0)
        toast("Saved ${settings.url()}")
    }

    private fun holdFill() = (unwell.background as LayerDrawable).findDrawableByLayerId(R.id.fill)

    private fun startHold() {
        unwell.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        unwell.text = "Keep holding…"
        hold = ValueAnimator.ofInt(0, 10_000).apply {
            duration = HOLD_MS
            interpolator = LinearInterpolator()
            addUpdateListener { holdFill().level = it.animatedValue as Int }
            addListener(object : AnimatorListenerAdapter() {
                private var cancelled = false
                override fun onAnimationCancel(animation: Animator) { cancelled = true }
                override fun onAnimationEnd(animation: Animator) {
                    hold = null
                    holdFill().level = 0
                    unwell.text = "Hold: I feel unwell"
                    if (!cancelled) sendCheckin()
                }
            })
            start()
        }
    }

    private fun cancelHold() {
        hold?.cancel()
    }

    private fun sendCheckin() {
        unwell.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
        LiveState.checkinText = "Sending…"
        LiveState.checkinOk = true
        startService(VitalsService.intent(this, VitalsService.ACTION_CHECKIN))
        refresh()
    }

    // --- Permissions -------------------------------------------------------------------------

    private fun foregroundPermissions(): List<String> = buildList {
        if (Build.VERSION.SDK_INT >= 36) {
            // Wear OS 6 replaced BODY_SENSORS with granular health permissions.
            add("android.permission.health.READ_HEART_RATE")
            add("android.permission.health.READ_OXYGEN_SATURATION")
            add("android.permission.health.READ_SKIN_TEMPERATURE")
        } else {
            add(Manifest.permission.BODY_SENSORS)
        }
        add(Manifest.permission.ACTIVITY_RECOGNITION)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun backgroundPermission(): String? = when {
        Build.VERSION.SDK_INT >= 36 -> "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND"
        Build.VERSION.SDK_INT >= 33 -> Manifest.permission.BODY_SENSORS_BACKGROUND
        else -> null
    }

    private fun missing(perms: List<String>) =
        perms.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }

    private fun requestPermissionsThenStart() {
        val need = missing(foregroundPermissions())
        if (need.isNotEmpty()) requestPermissions(need.toTypedArray(), REQ_FOREGROUND)
        else requestBackgroundThenStart()
    }

    /** Background sensor access must be asked for separately, after the foreground ones. */
    private fun requestBackgroundThenStart() {
        val bg = backgroundPermission()
        if (bg != null && missing(listOf(bg)).isNotEmpty() && missing(foregroundPermissions()).isEmpty()) {
            requestPermissions(arrayOf(bg), REQ_BACKGROUND)
        } else {
            startVitals()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            REQ_FOREGROUND -> requestBackgroundThenStart()
            REQ_BACKGROUND -> startVitals()
        }
    }

    private fun startVitals() {
        val denied = missing(foregroundPermissions() + listOfNotNull(backgroundPermission()))
        if (denied.isNotEmpty()) {
            // Still start: whatever can't be read is sent as null and listed on screen.
            LiveState.message = "Not granted: " + denied.joinToString { it.substringAfterLast('.') }
        }
        startForegroundService(VitalsService.intent(this, VitalsService.ACTION_START))
    }

    // --- Screen ------------------------------------------------------------------------------

    private fun refresh() {
        val now = System.currentTimeMillis()
        val s = LiveState.lastSnapshot.takeIf { LiveState.running }
        hr.text = s?.hr?.toString() ?: "--"
        spo2.text = s?.spo2?.let { "$it %" } ?: "--"
        skin.text = s?.skinTempC?.let { String.format(Locale.US, "%.1f °C", it) } ?: "--"

        val connected = LiveState.connected(now)
        when {
            !LiveState.running -> setLink("● Stopped", R.color.muted)
            connected -> setLink("● Connected", R.color.ok)
            else -> setLink("● Not connected", R.color.bad)
        }
        // One buzz when the board link drops while monitoring, so the wearer notices without looking.
        if (wasConnected && !connected && LiveState.running) link.performHapticFeedback(HapticFeedbackConstants.REJECT)
        wasConnected = connected

        linkDetail.text = buildString {
            append(settings.url().removePrefix("http://"))
            if (LiveState.running && LiveState.queued > 1) append("\n${LiveState.queued} samples waiting to send")
            if (!connected) LiveState.lastError?.let { append("\n").append(it) }
        }
        notes.text = listOfNotNull(LiveState.message, LiveState.notes.takeIf { LiveState.running && it.isNotBlank() })
            .joinToString("\n")

        if (shownRunning != LiveState.running) {   // restyle only on change, so a press in progress is not reset
            shownRunning = LiveState.running
            toggle.text = if (LiveState.running) "Stop monitoring" else "Start monitoring"
            toggle.setBackgroundResource(if (LiveState.running) R.drawable.pill_ghost else R.drawable.pill_primary)
            toggle.setTextColor(getColor(if (LiveState.running) R.color.paper else R.color.ink))
        }

        ecgStatus.text = EcgCheck.status

        LiveState.checkinText?.let {
            checkinStatus.text = it
            checkinStatus.setTextColor(getColor(if (LiveState.checkinOk) R.color.paper else R.color.bad))
        }
        if (LiveState.checkinAtMs != seenCheckinAt) {
            if (seenCheckinAt != 0L || now - LiveState.checkinAtMs < 5_000) {
                unwell.performHapticFeedback(
                    if (LiveState.checkinOk) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.REJECT
                )
            }
            seenCheckinAt = LiveState.checkinAtMs
        }
    }

    private fun setLink(text: String, colorRes: Int) {
        link.text = text
        link.setTextColor(getColor(colorRes))
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    companion object {
        private const val REQ_FOREGROUND = 1
        private const val REQ_BACKGROUND = 2
        private const val HOLD_MS = 1_000L
    }
}
