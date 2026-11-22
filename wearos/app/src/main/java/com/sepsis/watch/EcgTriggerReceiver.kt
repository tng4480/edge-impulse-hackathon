package com.sepsis.watch

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Starts one ECG + PPG check. Fire it from a button with
 * `sendBroadcast(Intent("com.sepsis.ECG_CHECK").setPackage(packageName))`, or from a shell with
 * `adb shell am broadcast -a com.sepsis.ECG_CHECK -n com.sepsis.watch/.EcgTriggerReceiver`.
 */
class EcgTriggerReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        EcgCheck.start(context)
    }
}
