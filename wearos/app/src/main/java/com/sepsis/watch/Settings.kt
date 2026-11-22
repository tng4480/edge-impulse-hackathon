package com.sepsis.watch

import android.content.Context

/** Board address, editable on the watch because the hotspot / venue Wi-Fi changes it. */
class Settings(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var host: String
        get() = prefs.getString(KEY_HOST, null) ?: DEFAULT_HOST
        set(value) = prefs.edit().putString(KEY_HOST, value.trim()).apply()

    var port: Int
        get() = prefs.getInt(KEY_PORT, DEFAULT_PORT)
        set(value) = prefs.edit().putInt(KEY_PORT, value).apply()

    fun url(): String = "http://$host:$port/vitals"

    companion object {
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"

        // fake: 10.0.2.2 is the emulator's alias for the laptop running tools/test_server.py.
        // real: the board's address on the S26ULTRA phone hotspot when this was built; editable on the watch.
        val DEFAULT_HOST = if (BuildConfig.FLAVOR == "fake") "10.0.2.2" else "10.136.49.240"
        const val DEFAULT_PORT = 8000
    }
}
