package com.sepsis.watch

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Buffers samples and POSTs them to the board, oldest first.
 *
 * Wear OS keeps Wi-Fi off while the phone is reachable over Bluetooth and routes traffic through
 * the phone, which cannot reach a LAN address like the board's. So we explicitly request a Wi-Fi
 * network (without requiring internet, since a hotspot or venue LAN may not have any) and open
 * connections on it.
 */
class Uplink(context: Context) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    @Volatile private var wifi: Network? = null
    private val queue = ArrayDeque<String>()

    private val wifiCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            wifi = network
        }

        override fun onLost(network: Network) {
            if (wifi == network) wifi = null
        }
    }

    fun start() {
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        try {
            cm.requestNetwork(request, wifiCallback)
        } catch (e: RuntimeException) {
            LiveState.lastError = "Wi-Fi request failed: ${e.message}"
        }
    }

    fun stop() {
        try {
            cm.unregisterNetworkCallback(wifiCallback)
        } catch (_: RuntimeException) {
        }
        wifi = null
    }

    @Synchronized
    fun enqueue(json: String) {
        queue.addLast(json)
        while (queue.size > MAX_QUEUE) queue.removeFirst()
    }

    @Synchronized
    fun queued(): Int = queue.size

    @Synchronized
    private fun peek(): String? = queue.firstOrNull()

    @Synchronized
    private fun remove(body: String) {
        if (queue.firstOrNull() === body) queue.removeFirst()
    }

    /** Sends queued samples oldest first and stops at the first network failure. Call off the main thread. */
    fun drain(url: String) {
        repeat(MAX_PER_DRAIN) {
            val body = peek() ?: return
            val code = post(url, body) ?: return // unreachable: keep it queued, retry next tick
            remove(body)
            if (code in 200..299) {
                LiveState.lastOkAtMs = System.currentTimeMillis()
                LiveState.lastError = null
            } else {
                // The board answered but refused this sample; retrying the same body won't help.
                LiveState.lastError = "Board replied HTTP $code (sample dropped)"
            }
        }
    }

    /** HTTP status, or null if the board could not be reached. */
    private fun post(url: String, body: String): Int? {
        val target = URL(url)
        // Wi-Fi first (see class doc); fall back to the default route (emulator, or watch without the phone).
        val wifiNow = wifi
        val routes: List<Network?> = if (wifiNow != null) listOf(wifiNow, null) else listOf(null)
        var lastError: IOException? = null
        for (network in routes) {
            try {
                val conn = (network?.openConnection(target) ?: target.openConnection()) as HttpURLConnection
                try {
                    conn.connectTimeout = 2_000
                    conn.readTimeout = 3_000
                    conn.requestMethod = "POST"
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    val code = conn.responseCode
                    try {
                        (if (code >= 400) conn.errorStream else conn.inputStream)?.use { it.readBytes() }
                    } catch (_: IOException) {
                    }
                    return code
                } finally {
                    conn.disconnect()
                }
            } catch (e: IOException) {
                lastError = e
            }
        }
        LiveState.lastError = "Board unreachable: ${lastError?.javaClass?.simpleName} ${lastError?.message ?: ""}".trim()
        return null
    }

    companion object {
        const val MAX_QUEUE = 720      // 1 hour of samples at one per 5 s
        const val MAX_PER_DRAIN = 30   // catch up gradually after an outage
    }
}
