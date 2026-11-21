package com.sepsis.watch

/** State the service publishes and the screen reads (same process, so a plain object is enough). */
object LiveState {
    /** The board counts as connected if a POST succeeded this recently. */
    private const val CONNECTED_WINDOW_MS = 12_000L

    @Volatile var running = false
    @Volatile var lastSnapshot: Snapshot? = null
    @Volatile var lastOkAtMs = 0L
    @Volatile var lastError: String? = null
    @Volatile var queued = 0
    @Volatile var notes = ""
    @Volatile var message: String? = null

    fun connected(nowMs: Long) = running && nowMs - lastOkAtMs <= CONNECTED_WINDOW_MS
}
