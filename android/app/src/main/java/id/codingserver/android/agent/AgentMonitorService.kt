package id.codingserver.android.agent

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import id.codingserver.android.CodingServerApp
import id.codingserver.android.MainActivity
import id.codingserver.android.R
import id.codingserver.android.data.api.AgentTask
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service yang memantau task AI Agent di server selama ada task aktif.
 *
 * Agen sendiri berjalan di server (Raspberry Pi); service ini hanya mem-polling status supaya:
 * * ada notifikasi tetap "Agent sedang bekerja…" berisi progres task aktif, dan
 * * muncul notifikasi saat task selesai, gagal, dijeda, atau menunggu persetujuan —
 *   walaupun aplikasi ditutup / layar mati.
 *
 * Service berhenti sendiri bila tidak ada lagi task aktif (task yang menunggu persetujuan
 * dianggap tidak aktif: agen diam sampai pengguna memutuskan; setelah disetujui aplikasi
 * menyalakan service lagi).
 */
class AgentMonitorService : Service() {

    companion object {
        const val EXTRA_OPEN_TASK = "id.codingserver.android.OPEN_AGENT_TASK"
        private const val ACTION_STOP = "id.codingserver.android.agent.STOP_MONITOR"
        private const val CH_ONGOING = "agent_ongoing"
        private const val CH_EVENTS = "agent_events"
        private const val NOTIF_ONGOING = 4100

        private const val POLL_MS = 4_000L
        private const val POLL_OFFLINE_MS = 10_000L
        /** Berhenti bila server tak terjangkau terus-menerus selama ±15 menit. */
        private const val MAX_FAILURES = 90

        val ACTIVE = setOf("PENDING", "PLANNING", "INSPECTING", "EXECUTING", "BUILDING", "TESTING", "REVIEWING", "FIXING")

        @Volatile var running = false
            private set

        /** Nyalakan pemantauan (aman dipanggil berulang). Hanya dari UI yang sedang tampil. */
        fun start(context: Context) {
            if (running) return
            runCatching {
                ContextCompat.startForegroundService(context, Intent(context, AgentMonitorService::class.java))
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, AgentMonitorService::class.java))
        }

        private fun stageLabel(s: String): String = when (s) {
            "PENDING" -> "Antre"
            "PLANNING" -> "Merencanakan"
            "INSPECTING" -> "Memeriksa proyek"
            "EXECUTING" -> "Mengerjakan"
            "WAITING_APPROVAL" -> "Menunggu persetujuan"
            "BUILDING" -> "Build"
            "TESTING" -> "Menguji"
            "REVIEWING" -> "Meninjau"
            "FIXING" -> "Memperbaiki"
            "COMPLETED" -> "Selesai"
            "FAILED" -> "Gagal"
            "CANCELLED" -> "Dibatalkan"
            "PAUSED" -> "Dijeda"
            else -> s
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var loop: Job? = null
    private val lastStatus = HashMap<String, String>()
    private var primed = false
    private val startedAtSec = System.currentTimeMillis() / 1000.0

    private val nm: NotificationManager get() = getSystemService(NotificationManager::class.java)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        running = true
        ensureChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopNow()
            return START_NOT_STICKY
        }
        // Wajib memanggil startForeground secepatnya setelah startForegroundService.
        val ok = runCatching {
            val type = when {
                Build.VERSION.SDK_INT >= 34 -> ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
                Build.VERSION.SDK_INT >= 29 -> ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
                else -> 0
            }
            ServiceCompat.startForeground(this, NOTIF_ONGOING, ongoing("Agent AI", "Menghubungkan ke server…", null, null), type)
        }.isSuccess
        if (!ok) {
            stopNow()
            return START_NOT_STICKY
        }
        if (loop?.isActive != true) loop = scope.launch { monitor() }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        scope.cancel()
        super.onDestroy()
    }

    private fun stopNow() {
        loop?.cancel()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private suspend fun monitor() {
        val app = application as CodingServerApp
        val server = app.servers.current()
        if (server == null || app.tokens.get(server.id) == null) {
            stopNow(); return
        }
        var expired = false
        val client = ApiClient(server, app.tokens) { expired = true }
        var failures = 0
        while (scope.isActive) {
            val res = apiCall { client.api.agentTasks() }
            if (expired) {
                postEvent("session", "Sesi berakhir", "Login lagi di aplikasi untuk melanjutkan pemantauan agent.", null)
                stopNow(); return
            }
            val tasks = res.getOrNull()?.tasks
            if (tasks != null) {
                failures = 0
                handleTransitions(tasks)
                val active = tasks.filter { it.status in ACTIVE }
                if (active.isEmpty()) {
                    stopNow(); return
                }
                showActive(active)
            } else {
                failures++
                if (failures >= MAX_FAILURES) {
                    postEvent("offline", "Pemantauan agent berhenti", "Server tidak bisa dihubungi. Agent tetap berjalan di server.", null)
                    stopNow(); return
                }
                nm.notify(NOTIF_ONGOING, ongoing("Agent AI", "Server tidak terjangkau, mencoba lagi…", null, null))
            }
            delay(if (failures > 0) POLL_OFFLINE_MS else POLL_MS)
        }
    }

    private fun handleTransitions(tasks: List<AgentTask>) {
        for (t in tasks) {
            val prev = lastStatus.put(t.id, t.status)
            if (!primed || prev == t.status) continue
            // Task baru yang belum pernah terlihat: hanya beri tahu bila berubah setelah service mulai.
            if (prev == null && t.updated_at < startedAtSec) continue
            when (t.status) {
                "WAITING_APPROVAL" -> postEvent(t.id, "Butuh persetujuan",
                    "${t.title}: ${t.pending_proposals.coerceAtLeast(1)} perubahan menunggu keputusanmu", t)
                "COMPLETED" -> postEvent(t.id, "Task selesai ✓", t.title, t)
                "FAILED" -> postEvent(t.id, "Task gagal", t.title + (t.error.takeIf { it.isNotBlank() }?.let { "\n$it" } ?: ""), t)
                "PAUSED" -> postEvent(t.id, "Task dijeda", t.title + (t.current_op.takeIf { it.isNotBlank() }?.let { "\n$it" } ?: ""), t)
            }
        }
        primed = true
    }

    private fun showActive(active: List<AgentTask>) {
        val t = active.first()
        val more = if (active.size > 1) " (+${active.size - 1} task lain)" else ""
        val text = stageLabel(t.status) + (t.current_op.takeIf { it.isNotBlank() }?.let { " · $it" } ?: "")
        nm.notify(NOTIF_ONGOING, ongoing("Agent bekerja: ${t.title}$more", text, t.progress, t))
    }

    // ---------- notifikasi ----------

    private fun ensureChannels() {
        if (Build.VERSION.SDK_INT < 26) return
        nm.createNotificationChannel(NotificationChannel(CH_ONGOING, "Agent sedang bekerja", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Progres task AI Agent yang sedang berjalan di server"
            setShowBadge(false)
        })
        nm.createNotificationChannel(NotificationChannel(CH_EVENTS, "Status task Agent", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Task selesai, gagal, dijeda, atau menunggu persetujuan"
        })
    }

    private fun openIntent(task: AgentTask?): PendingIntent {
        val i = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            if (task != null) putExtra(EXTRA_OPEN_TASK, task.id)
        }
        return PendingIntent.getActivity(this, task?.id?.hashCode() ?: 0, i,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun ongoing(title: String, text: String, progress: Double?, task: AgentTask?): android.app.Notification {
        val stop = PendingIntent.getService(this, 1, Intent(this, AgentMonitorService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val b = NotificationCompat.Builder(this, CH_ONGOING)
            .setSmallIcon(R.drawable.ic_stat_agent)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(openIntent(task))
            .addAction(0, "Berhenti memantau", stop)
        if (progress == null) b.setProgress(0, 0, true)
        else b.setProgress(100, (progress * 100).toInt().coerceIn(0, 100), false)
        return b.build()
    }

    private fun postEvent(key: String, title: String, text: String, task: AgentTask?) {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val n = NotificationCompat.Builder(this, CH_EVENTS)
            .setSmallIcon(R.drawable.ic_stat_agent)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setAutoCancel(true)
            .setContentIntent(openIntent(task))
            .build()
        nm.notify("agent_event", key.hashCode(), n)
    }
}
