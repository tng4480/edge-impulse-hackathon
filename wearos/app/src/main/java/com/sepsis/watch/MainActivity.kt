package com.sepsis.watch

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
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
    private lateinit var host: EditText
    private lateinit var port: EditText

    private val ui = Handler(Looper.getMainLooper())
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
        host = findViewById(R.id.host)
        port = findViewById(R.id.port)

        findViewById<View>(R.id.fakeBanner).visibility =
            if (BuildConfig.FLAVOR == "fake") View.VISIBLE else View.GONE
        applyAddressExtras(intent)

        toggle.setOnClickListener {
            if (LiveState.running) {
                startService(VitalsService.intent(this, VitalsService.ACTION_STOP))
            } else {
                requestPermissionsThenStart()
            }
        }
        findViewById<Button>(R.id.measureSpo2).setOnClickListener {
            if (LiveState.running) {
                startService(VitalsService.intent(this, VitalsService.ACTION_SPO2))
            } else {
                toast("Press Start first")
            }
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
        hr.text = "HR " + (s?.hr?.let { "$it bpm" } ?: "--")
        spo2.text = "SpO2 " + (s?.spo2?.let { "$it %" } ?: "--")
        skin.text = "Skin " + (s?.skinTempC?.let { String.format(Locale.US, "%.1f °C", it) } ?: "--")

        when {
            !LiveState.running -> setLink("● Stopped", Color.GRAY)
            LiveState.connected(now) -> setLink("● Connected", Color.rgb(0x66, 0xBB, 0x6A))
            else -> setLink("● Not connected", Color.rgb(0xEF, 0x53, 0x50))
        }
        linkDetail.text = buildString {
            append(settings.url().removePrefix("http://"))
            if (LiveState.running) append("\nqueued ${LiveState.queued}")
            if (!LiveState.connected(now)) LiveState.lastError?.let { append("\n").append(it) }
        }
        notes.text = listOfNotNull(LiveState.message, LiveState.notes.takeIf { LiveState.running && it.isNotBlank() })
            .joinToString("\n")
        toggle.text = if (LiveState.running) "Stop" else "Start"
    }

    private fun setLink(text: String, color: Int) {
        link.text = text
        link.setTextColor(color)
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    companion object {
        private const val REQ_FOREGROUND = 1
        private const val REQ_BACKGROUND = 2
    }
}
