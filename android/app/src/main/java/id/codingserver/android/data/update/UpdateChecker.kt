package id.codingserver.android.data.update

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import id.codingserver.android.BuildConfig
import id.codingserver.android.MainActivity
import id.codingserver.android.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Pemeriksa pembaruan otomatis: dipanggil saat aplikasi dibuka/kembali tampil dan berkala (lihat AppViewModel).
 * Bila ada build baru di GitHub Releases -> [available] terisi (banner di aplikasi) dan notifikasi sistem
 * dikirim SEKALI per build (tidak mengganggu berulang-ulang).
 */
object UpdateChecker {
    const val EXTRA_OPEN_ROUTE = "id.codingserver.android.OPEN_ROUTE"
    private const val CHANNEL = "app_update"
    private const val NOTIF_ID = 4200
    private const val PREFS = "update_checker"
    private const val KEY_NOTIFIED = "notified_build"
    private const val MIN_INTERVAL_MS = 30 * 60 * 1000L

    private val _available = MutableStateFlow<AppRelease?>(null)
    /** Rilis yang lebih baru dari APK terpasang, atau null. */
    val available: StateFlow<AppRelease?> = _available.asStateFlow()

    private val updater = AppUpdater()
    private val mutex = Mutex()
    private var lastCheck = 0L

    /** Periksa GitHub (dibatasi tiap 30 menit kecuali [force]). Gagal jaringan diabaikan diam-diam. */
    suspend fun check(context: Context, force: Boolean = false): AppRelease? = mutex.withLock {
        val now = System.currentTimeMillis()
        if (!force && now - lastCheck < MIN_INTERVAL_MS) return@withLock _available.value
        lastCheck = now
        val r = if (force) updater.latest() else runCatching { updater.latest() }.getOrNull() ?: return@withLock _available.value
        if (r.build > BuildConfig.VERSION_CODE) {
            _available.value = r
            notifyOnce(context.applicationContext, r)
        } else {
            _available.value = null
            cancel(context)
        }
        _available.value
    }

    fun cancel(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(NOTIF_ID)
    }

    private fun notifyOnce(ctx: Context, r: AppRelease) {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getInt(KEY_NOTIFIED, 0) >= r.build) return
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val nm = ctx.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Pembaruan aplikasi", NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = "Kabar bila ada APK Coding Server versi baru" })
        }
        val open = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_OPEN_ROUTE, "settings")
        }
        val pi = PendingIntent.getActivity(ctx, NOTIF_ID, open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_agent)
            .setContentTitle("Pembaruan Coding Server tersedia")
            .setContentText("Build ${r.build} siap dipasang (terpasang: build ${BuildConfig.VERSION_CODE}). Ketuk untuk memperbarui.")
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "${r.title}\nTerpasang: build ${BuildConfig.VERSION_CODE}. Ketuk untuk membuka Pengaturan → Pembaruan aplikasi."))
            .setAutoCancel(true)
            .setContentIntent(pi)
            .addAction(0, "Perbarui", pi)
            .build()
        nm.notify(NOTIF_ID, n)
        prefs.edit().putInt(KEY_NOTIFIED, r.build).apply()
    }
}
