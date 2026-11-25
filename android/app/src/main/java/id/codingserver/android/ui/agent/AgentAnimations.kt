package id.codingserver.android.ui.agent

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AgentTask
import id.codingserver.android.ui.common.formatDuration
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/** Fase yang ditampilkan ke pengguna (lebih rinci dari status server: ada "Berpikir"). */
enum class AgentPhase(val title: String, val color: Color, val active: Boolean) {
    QUEUED("Mengantre", Color(0xFF78909C), true),
    THINKING("Berpikir", Color(0xFF8E24AA), true),
    INSPECTING("Memeriksa proyek", Color(0xFF00897B), true),
    PLANNING("Merencanakan", Color(0xFF3949AB), true),
    WORKING("Mengerjakan", WarnAmber, true),
    FIXING("Memperbaiki", Color(0xFFF4511E), true),
    BUILDING("Build", Color(0xFF6D4C41), true),
    TESTING("Menguji", Color(0xFF039BE5), true),
    REVIEWING("Meninjau", Color(0xFF5E35B1), true),
    WAITING("Menunggu persetujuanmu", Color(0xFF1E88E5), false),
    PAUSED("Dijeda", Color(0xFF78909C), false),
    DONE("Selesai!", OkGreen, false),
    FAILED("Gagal", ErrRed, false),
    CANCELLED("Dibatalkan", Color(0xFF78909C), false),
}

private fun statusPhase(status: String): AgentPhase = when (status) {
    "PENDING" -> AgentPhase.QUEUED
    "PLANNING" -> AgentPhase.PLANNING
    "INSPECTING" -> AgentPhase.INSPECTING
    "EXECUTING" -> AgentPhase.WORKING
    "FIXING" -> AgentPhase.FIXING
    "BUILDING" -> AgentPhase.BUILDING
    "TESTING" -> AgentPhase.TESTING
    "REVIEWING" -> AgentPhase.REVIEWING
    "WAITING_APPROVAL" -> AgentPhase.WAITING
    "PAUSED" -> AgentPhase.PAUSED
    "COMPLETED" -> AgentPhase.DONE
    "FAILED" -> AgentPhase.FAILED
    "CANCELLED" -> AgentPhase.CANCELLED
    else -> AgentPhase.WORKING
}

/**
 * Fase sekarang. Selama task aktif, event terakhir "thinking" (atau "observation": model akan dipanggil lagi)
 * berarti model AI sedang menyusun langkah berikutnya → animasi "Berpikir".
 */
fun agentPhase(status: String, lastEventKind: String?): AgentPhase {
    val p = statusPhase(status)
    if (!p.active || p == AgentPhase.QUEUED) return p
    return if (lastEventKind == "thinking" || lastEventKind == "observation") AgentPhase.THINKING else p
}

fun agentPhase(status: String): AgentPhase = statusPhase(status)

// =====================================================================================
// Animasi ikon per fase (digambar dengan Canvas, tanpa aset tambahan)
// =====================================================================================

@Composable
fun AgentAnimation(phase: AgentPhase, size: Dp, modifier: Modifier = Modifier) {
    AnimatedContent(
        targetState = phase, modifier = modifier.size(size), label = "agentAnim",
        transitionSpec = { (scaleIn(tween(350), 0.6f) + fadeIn(tween(350))) togetherWith (scaleOut(tween(250), 0.6f) + fadeOut(tween(250))) },
    ) { p ->
        Box(Modifier.size(size)) {
            when (p) {
                AgentPhase.THINKING -> ThinkingAnim(p.color)
                AgentPhase.INSPECTING, AgentPhase.REVIEWING -> InspectAnim(p.color)
                AgentPhase.PLANNING -> PlanningAnim(p.color)
                AgentPhase.WORKING, AgentPhase.FIXING -> GearsAnim(p.color)
                AgentPhase.BUILDING -> BuildAnim(p.color)
                AgentPhase.TESTING -> TestAnim(p.color)
                AgentPhase.WAITING, AgentPhase.QUEUED -> ClockAnim(p.color)
                AgentPhase.DONE -> DoneAnim(p.color)
                AgentPhase.FAILED -> FailedAnim(p.color)
                AgentPhase.PAUSED -> PausedAnim(p.color)
                AgentPhase.CANCELLED -> CancelledAnim(p.color)
            }
        }
    }
}

private fun DrawScope.halo(color: Color, pulse: Float) {
    val r = size.minDimension / 2
    drawCircle(color.copy(alpha = 0.10f + 0.08f * pulse), radius = r * (0.88f + 0.12f * pulse))
    drawCircle(color.copy(alpha = 0.14f), radius = r * 0.78f)
}

@Composable
private fun ThinkingAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "think")
    val t by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1400, easing = LinearEasing)), label = "t")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        val c = center
        halo(color, pulse)
        // Gelembung pikiran
        drawCircle(color, radius = s * 0.30f, center = c, style = Stroke(s * 0.035f))
        drawCircle(color.copy(alpha = 0.7f), radius = s * 0.045f, center = c + Offset(-s * 0.24f, s * 0.30f))
        drawCircle(color.copy(alpha = 0.5f), radius = s * 0.028f, center = c + Offset(-s * 0.33f, s * 0.40f))
        // Tiga titik melompat bergantian
        for (i in 0..2) {
            val ph = ((t - i * 0.18f) % 1f + 1f) % 1f
            val jump = max(0f, sin(ph * 2 * PI.toFloat())) * s * 0.08f
            drawCircle(color, radius = s * 0.045f, center = Offset(c.x + (i - 1) * s * 0.13f, c.y - jump))
        }
        // Percikan ide yang mengorbit
        for (k in 0..1) {
            val a = (t + k * 0.5f) * 2 * PI.toFloat()
            val p = c + Offset(cos(a) * s * 0.42f, sin(a) * s * 0.42f)
            sparkle(p, s * 0.05f * (0.6f + 0.4f * pulse), color.copy(alpha = 0.9f))
        }
    }
}

private fun DrawScope.sparkle(p: Offset, r: Float, color: Color) {
    drawLine(color, p + Offset(-r, 0f), p + Offset(r, 0f), r * 0.35f, StrokeCap.Round)
    drawLine(color, p + Offset(0f, -r), p + Offset(0f, r), r * 0.35f, StrokeCap.Round)
}

@Composable
private fun InspectAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "inspect")
    val t by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(2400, easing = LinearEasing)), label = "t")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        // Dokumen
        val dl = s * 0.24f; val dt = s * 0.20f
        drawRoundRect(color.copy(alpha = 0.25f), Offset(dl, dt), Size(s * 0.46f, s * 0.58f), CornerRadius(s * 0.05f))
        for (i in 0..3) {
            val w = if (i == 3) 0.22f else 0.34f
            drawLine(color.copy(alpha = 0.6f), Offset(dl + s * 0.06f, dt + s * (0.12f + i * 0.11f)),
                     Offset(dl + s * (0.06f + w), dt + s * (0.12f + i * 0.11f)), s * 0.03f, StrokeCap.Round)
        }
        // Kaca pembesar menyapu dokumen
        val a = t * 2 * PI.toFloat()
        val lc = center + Offset(cos(a) * s * 0.13f, sin(2 * a) * s * 0.10f) - Offset(s * 0.02f, s * 0.04f)
        val lr = s * 0.15f
        drawCircle(Color.White.copy(alpha = 0.35f), lr, lc)
        drawCircle(color, lr, lc, style = Stroke(s * 0.045f))
        val h0 = lc + Offset(lr * 0.72f, lr * 0.72f)
        drawLine(color, h0, h0 + Offset(s * 0.13f, s * 0.13f), s * 0.07f, StrokeCap.Round)
    }
}

@Composable
private fun PlanningAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "plan")
    val t by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(3000, easing = LinearEasing)), label = "t")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        // Papan klip
        val l = s * 0.24f; val top = s * 0.17f; val w = s * 0.52f; val h = s * 0.66f
        drawRoundRect(color.copy(alpha = 0.22f), Offset(l, top), Size(w, h), CornerRadius(s * 0.06f))
        drawRoundRect(color, Offset(l + w * 0.3f, top - s * 0.04f), Size(w * 0.4f, s * 0.09f), CornerRadius(s * 0.03f))
        // Tiga baris rencana ditulis satu per satu, lalu dicentang
        val prog = min(1f, t * 1.25f) * 3f
        var pen: Offset? = null
        for (i in 0..2) {
            val y = top + s * (0.20f + i * 0.16f)
            val box = Offset(l + s * 0.06f, y - s * 0.045f)
            drawRoundRect(color, box, Size(s * 0.09f, s * 0.09f), CornerRadius(s * 0.02f), style = Stroke(s * 0.022f))
            val f = (prog - i).coerceIn(0f, 1f)
            val x0 = l + s * 0.20f; val x1 = l + w - s * 0.06f
            if (f > 0f) {
                val xe = x0 + (x1 - x0) * f
                drawLine(color.copy(alpha = 0.8f), Offset(x0, y), Offset(xe, y), s * 0.03f, StrokeCap.Round)
                if (f < 1f) pen = Offset(xe, y)
            }
            if (f >= 1f) {
                val b = box + Offset(s * 0.015f, s * 0.045f)
                drawLine(OkGreen, b, b + Offset(s * 0.025f, s * 0.025f), s * 0.025f, StrokeCap.Round)
                drawLine(OkGreen, b + Offset(s * 0.025f, s * 0.025f), b + Offset(s * 0.07f, -s * 0.03f), s * 0.025f, StrokeCap.Round)
            }
        }
        // Pensil (ujung tulisan)
        pen?.let {
            drawLine(WarnAmber, it + Offset(s * 0.02f, -s * 0.02f), it + Offset(s * 0.11f, -s * 0.11f), s * 0.05f, StrokeCap.Round)
            drawCircle(Color.DarkGray, s * 0.018f, it)
        }
    }
}

private fun DrawScope.gear(center: Offset, r: Float, teeth: Int, angle: Float, color: Color) {
    rotate(angle, center) {
        for (i in 0 until teeth) {
            rotate(360f / teeth * i, center) {
                drawRoundRect(color, Offset(center.x - r * 0.16f, center.y - r * 1.22f), Size(r * 0.32f, r * 0.4f), CornerRadius(r * 0.06f))
            }
        }
        drawCircle(color, r, center)
        drawCircle(Color.White.copy(alpha = 0.85f), r * 0.38f, center)
    }
}

@Composable
private fun GearsAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "gears")
    val a by tr.animateFloat(0f, 360f, infiniteRepeatable(tween(2600, easing = LinearEasing)), label = "a")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(800), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        gear(Offset(s * 0.42f, s * 0.45f), s * 0.19f, 8, a, color)
        gear(Offset(s * 0.68f, s * 0.66f), s * 0.12f, 6, -a * 1.6f + 15f, color.copy(alpha = 0.75f))
        sparkle(Offset(s * 0.74f, s * 0.26f), s * 0.05f * pulse, color)
    }
}

@Composable
private fun BuildAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "build")
    val t by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(2200, easing = LinearEasing)), label = "t")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        val bw = s * 0.22f; val bh = s * 0.15f
        val slots = listOf(Offset(s * 0.27f, s * 0.62f), Offset(s * 0.51f, s * 0.62f), Offset(s * 0.39f, s * 0.46f), Offset(s * 0.39f, s * 0.30f))
        slots.forEachIndexed { i, slot ->
            val start = i * 0.18f
            val f = ((t - start) / 0.18f).coerceIn(0f, 1f)
            if (t >= start) {
                val ease = 1f - (1f - f) * (1f - f)
                val y = slot.y - (1f - ease) * s * 0.35f
                val alpha = if (t > 0.9f) (1f - (t - 0.9f) / 0.1f) else 1f
                drawRoundRect(color.copy(alpha = alpha), Offset(slot.x, y), Size(bw, bh), CornerRadius(s * 0.025f))
                drawRoundRect(Color.White.copy(alpha = 0.35f * alpha), Offset(slot.x + bw * 0.12f, y + bh * 0.2f), Size(bw * 0.3f, bh * 0.25f), CornerRadius(s * 0.01f))
            }
        }
        drawLine(color.copy(alpha = 0.5f), Offset(s * 0.2f, s * 0.78f), Offset(s * 0.8f, s * 0.78f), s * 0.025f, StrokeCap.Round)
    }
}

@Composable
private fun TestAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "test")
    val t by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "t")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        // Labu uji
        val flask = Path().apply {
            moveTo(s * 0.42f, s * 0.20f); lineTo(s * 0.42f, s * 0.42f); lineTo(s * 0.25f, s * 0.74f)
            quadraticTo(s * 0.23f, s * 0.80f, s * 0.30f, s * 0.80f); lineTo(s * 0.70f, s * 0.80f)
            quadraticTo(s * 0.77f, s * 0.80f, s * 0.75f, s * 0.74f); lineTo(s * 0.58f, s * 0.42f); lineTo(s * 0.58f, s * 0.20f)
        }
        val liquidTop = s * (0.58f - 0.02f * sin(t * 2 * PI.toFloat()))
        val liquid = Path().apply {
            moveTo(s * 0.34f, liquidTop); lineTo(s * 0.66f, liquidTop); lineTo(s * 0.75f, s * 0.74f)
            quadraticTo(s * 0.77f, s * 0.80f, s * 0.70f, s * 0.80f); lineTo(s * 0.30f, s * 0.80f)
            quadraticTo(s * 0.23f, s * 0.80f, s * 0.25f, s * 0.74f); close()
        }
        drawPath(liquid, color.copy(alpha = 0.55f))
        drawPath(flask, color, style = Stroke(s * 0.04f, cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawLine(color, Offset(s * 0.37f, s * 0.20f), Offset(s * 0.63f, s * 0.20f), s * 0.04f, StrokeCap.Round)
        // Gelembung naik
        for (i in 0..3) {
            val ph = (t + i * 0.25f) % 1f
            val x = s * (0.44f + 0.12f * sin((ph * 3 + i) * PI.toFloat()) * 0.5f + (i % 2) * 0.06f)
            val y = s * 0.76f - ph * s * 0.62f
            drawCircle(color.copy(alpha = (1f - ph) * 0.9f), s * (0.025f + 0.015f * ph), Offset(x, y), style = Stroke(s * 0.015f))
        }
    }
}

@Composable
private fun ClockAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "clock")
    val a by tr.animateFloat(0f, 360f, infiniteRepeatable(tween(2400, easing = LinearEasing)), label = "a")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        val c = center
        halo(color, pulse)
        drawCircle(color, s * 0.30f, c, style = Stroke(s * 0.04f))
        for (i in 0 until 12) rotate(i * 30f, c) {
            drawLine(color.copy(alpha = 0.6f), Offset(c.x, c.y - s * 0.26f), Offset(c.x, c.y - s * 0.23f), s * 0.015f)
        }
        rotate(a, c) { drawLine(color, c, Offset(c.x, c.y - s * 0.22f), s * 0.035f, StrokeCap.Round) }
        rotate(a / 12f + 90f, c) { drawLine(color, c, Offset(c.x, c.y - s * 0.15f), s * 0.045f, StrokeCap.Round) }
        drawCircle(color, s * 0.035f, c)
    }
}

@Composable
private fun PausedAnim(color: Color) {
    val tr = rememberInfiniteTransition(label = "paused")
    val pulse by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1600), RepeatMode.Reverse), label = "p")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        halo(color, pulse)
        val bw = s * 0.1f; val bh = s * 0.36f
        drawRoundRect(color, Offset(s * 0.37f, s * 0.32f), Size(bw, bh), CornerRadius(s * 0.03f))
        drawRoundRect(color, Offset(s * 0.53f, s * 0.32f), Size(bw, bh), CornerRadius(s * 0.03f))
    }
}

@Composable
private fun CancelledAnim(color: Color) {
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        drawCircle(color.copy(alpha = 0.15f), s * 0.46f)
        drawCircle(color, s * 0.28f, style = Stroke(s * 0.05f))
        drawLine(color, center + Offset(-s * 0.2f, s * 0.2f), center + Offset(s * 0.2f, -s * 0.2f), s * 0.05f, StrokeCap.Round)
    }
}

/** Gambar polyline sebagian (0..1) — untuk efek "digoreskan". */
private fun DrawScope.partialPolyline(points: List<Offset>, fraction: Float, color: Color, width: Float) {
    val segs = points.zipWithNext()
    val total = segs.sumOf { (a, b) -> (b - a).getDistance().toDouble() }.toFloat()
    var remain = total * fraction.coerceIn(0f, 1f)
    for ((a, b) in segs) {
        if (remain <= 0f) break
        val len = (b - a).getDistance()
        val f = min(1f, remain / len)
        drawLine(color, a, a + (b - a) * f, width, StrokeCap.Round)
        remain -= len
    }
}

private data class Confetti(val angle: Float, val speed: Float, val color: Color, val size: Float, val spin: Float)

@Composable
private fun DoneAnim(color: Color) {
    val circle = remember { Animatable(0f) }
    val check = remember { Animatable(0f) }
    val burst = remember { Animatable(0f) }
    val confetti = remember {
        val palette = listOf(OkGreen, WarnAmber, Color(0xFF1E88E5), Color(0xFFE91E63), Color(0xFF8E24AA), Color(0xFF00ACC1))
        List(18) { Confetti(Random.nextFloat() * 360f, 0.35f + Random.nextFloat() * 0.25f, palette[it % palette.size], 0.025f + Random.nextFloat() * 0.02f, Random.nextFloat() * 720f - 360f) }
    }
    LaunchedEffect(Unit) {
        launch { circle.animateTo(1f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessLow)) }
        delay(250)
        launch { burst.animateTo(1f, tween(1300, easing = LinearEasing)) }
        check.animateTo(1f, tween(450, easing = FastOutSlowInEasing))
    }
    val tr = rememberInfiniteTransition(label = "done")
    val glow by tr.animateFloat(0f, 1f, infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "g")
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        val c = center
        val sc = circle.value
        drawCircle(color.copy(alpha = 0.12f + 0.10f * glow * check.value), s * 0.48f * sc)
        drawCircle(color, s * 0.32f * sc, c)
        partialPolyline(
            listOf(c + Offset(-s * 0.14f, s * 0.0f), c + Offset(-s * 0.04f, s * 0.10f), c + Offset(s * 0.15f, -s * 0.10f)),
            check.value, Color.White, s * 0.06f,
        )
        // Konfeti meledak lalu jatuh
        val b = burst.value
        if (b in 0.001f..0.999f) for (p in confetti) {
            val rad = p.angle * PI.toFloat() / 180f
            val dist = s * p.speed * (1f - (1f - b) * (1f - b))
            val pos = c + Offset(cos(rad) * dist, sin(rad) * dist + s * 0.25f * b * b)
            translate(pos.x, pos.y) {
                rotate(p.spin * b, Offset.Zero) {
                    drawRect(p.color.copy(alpha = 1f - b), Offset(-s * p.size, -s * p.size * 0.5f), Size(s * p.size * 2, s * p.size))
                }
            }
        }
    }
}

@Composable
private fun FailedAnim(color: Color) {
    val circle = remember { Animatable(0f) }
    val cross = remember { Animatable(0f) }
    val shake = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        circle.animateTo(1f, spring(Spring.DampingRatioMediumBouncy, Spring.StiffnessMediumLow))
        cross.animateTo(1f, tween(380))
        shake.animateTo(1f, tween(600, easing = LinearEasing))
    }
    Canvas(Modifier.fillMaxSize()) {
        val s = size.minDimension
        val dx = sin(shake.value * PI.toFloat() * 8) * (1f - shake.value) * s * 0.07f
        translate(dx, 0f) {
            val c = center
            drawCircle(color.copy(alpha = 0.14f), s * 0.46f * circle.value)
            drawCircle(color, s * 0.32f * circle.value, c)
            val k = s * 0.12f
            partialPolyline(listOf(c + Offset(-k, -k), c + Offset(k, k)), cross.value * 2f, Color.White, s * 0.06f)
            partialPolyline(listOf(c + Offset(k, -k), c + Offset(-k, k)), cross.value * 2f - 1f, Color.White, s * 0.06f)
        }
    }
}

// =====================================================================================
// Kartu status utama + jalur tahapan
// =====================================================================================

@Composable
private fun AnimatedDots(color: Color) {
    val tr = rememberInfiniteTransition(label = "dots")
    val n by tr.animateFloat(0f, 4f, infiniteRepeatable(tween(1600, easing = LinearEasing)), label = "n")
    Text(".".repeat(n.toInt().coerceIn(0, 3)).padEnd(3, ' '), color = color, style = MaterialTheme.typography.titleMedium,
         fontWeight = FontWeight.Bold)
}

/** Kartu besar di atas detail task: animasi fase, langkah yang sedang dikerjakan, progres, waktu, dan tahapan. */
@Composable
fun AgentStatusHero(t: AgentTask, lastEventKind: String?, lastThought: String?, lastStage: String?) {
    val phase = agentPhase(t.status, lastEventKind)
    val prog by animateFloatAsState(t.progress.toFloat().coerceIn(0f, 1f), tween(900), label = "prog")
    val bg by androidx.compose.animation.animateColorAsState(phase.color.copy(alpha = 0.10f), tween(500), label = "bg")

    // Waktu berjalan (detik) — berdetak tiap detik selama task aktif.
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(phase.active) { while (phase.active) { now = System.currentTimeMillis(); delay(1000) } }
    val elapsed = when {
        t.duration != null && !phase.active -> t.duration.toLong()
        t.started_at != null -> max(0L, now / 1000 - t.started_at.toLong())
        else -> null
    }

    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = bg)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                AgentAnimation(phase, 84.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        AnimatedContent(phase, label = "title", transitionSpec = {
                            (fadeIn(tween(300)) + slideInVertically(tween(300)) { it / 2 }) togetherWith
                                (fadeOut(tween(200)) + slideOutVertically(tween(200)) { -it / 2 })
                        }) { p ->
                            Text(p.title, color = p.color, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        }
                        if (phase.active) AnimatedDots(phase.color)
                    }
                    if (phase == AgentPhase.THINKING) {
                        val stage = agentPhase(t.status)
                        Text("tahap: ${stage.title}", style = MaterialTheme.typography.labelSmall, color = stage.color)
                    }
                    val detail = when {
                        phase == AgentPhase.THINKING && !lastThought.isNullOrBlank() -> "💭 $lastThought"
                        phase == AgentPhase.FAILED && t.error.isNotBlank() -> t.error
                        else -> t.current_op
                    }
                    AnimatedContent(detail, label = "op", transitionSpec = { fadeIn(tween(300)) togetherWith fadeOut(tween(150)) }) { d ->
                        if (d.isNotBlank()) Text(d, style = MaterialTheme.typography.bodySmall, maxLines = 3, overflow = TextOverflow.Ellipsis,
                                                 fontStyle = if (d.startsWith("💭")) FontStyle.Italic else FontStyle.Normal,
                                                 color = if (phase == AgentPhase.FAILED) ErrRed else Color.Unspecified)
                    }
                }
            }
            // Progres
            Row(verticalAlignment = Alignment.CenterVertically) {
                LinearProgressIndicator(
                    progress = { prog }, color = phase.color, trackColor = phase.color.copy(alpha = 0.18f),
                    modifier = Modifier.weight(1f).height(8.dp).clip(RoundedCornerShape(4.dp)),
                )
                Spacer(Modifier.width(8.dp))
                Text("${(prog * 100).toInt()}%", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
            }
            val planDone = t.plan.count { it.status == "done" }
            Text(
                listOfNotNull(
                    "langkah ${t.steps_used}/${t.max_steps}",
                    t.plan.takeIf { it.isNotEmpty() }?.let { "rencana $planDone/${it.size}" },
                    elapsed?.let { "⏱ ${formatDuration(it)}" },
                    t.model,
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
            )
            StageStepper(t.status, lastStage)
        }
    }
}

private val PIPELINE = listOf("Periksa", "Rencana", "Kerjakan", "Uji", "Tinjau", "Selesai")

private fun pipelineIndex(status: String?): Int = when (status) {
    "INSPECTING" -> 0
    "PLANNING" -> 1
    "EXECUTING", "FIXING", "WAITING_APPROVAL" -> 2
    "BUILDING", "TESTING" -> 3
    "REVIEWING" -> 4
    "COMPLETED" -> 5
    else -> -1
}

/** Jalur tahapan: tahap selesai hijau, tahap sekarang berdenyut, tahap gagal merah. */
@Composable
private fun StageStepper(status: String, lastStage: String?) {
    val cur = pipelineIndex(status).takeIf { it >= 0 } ?: pipelineIndex(lastStage)
    val failed = status == "FAILED"
    val stopped = status == "PAUSED" || status == "CANCELLED"
    val tr = rememberInfiniteTransition(label = "stepper")
    val pulse by tr.animateFloat(0.55f, 1f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "pulse")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        PIPELINE.forEachIndexed { i, name ->
            val done = i < cur || status == "COMPLETED"
            val isCur = i == cur && status != "COMPLETED"
            val col = when {
                done -> OkGreen
                isCur && failed -> ErrRed
                isCur && stopped -> Color(0xFF78909C)
                isCur -> agentPhase(status).color
                else -> Color.Gray.copy(alpha = 0.35f)
            }
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f).height(2.dp).background(if (i == 0) Color.Transparent else if (done || isCur) OkGreen.copy(alpha = 0.6f) else Color.Gray.copy(alpha = 0.25f)))
                    val sz = if (isCur) 14.dp else 10.dp
                    Box(Modifier.size(sz).clip(RoundedCornerShape(50))
                        .background(if (isCur && !failed && !stopped) col.copy(alpha = pulse) else col),
                        contentAlignment = Alignment.Center) {}
                    Box(Modifier.weight(1f).height(2.dp).background(if (i == PIPELINE.lastIndex) Color.Transparent else if (done) OkGreen.copy(alpha = 0.6f) else Color.Gray.copy(alpha = 0.25f)))
                }
                Text(name, style = MaterialTheme.typography.labelSmall, maxLines = 1,
                     color = if (isCur) col else Color.Unspecified,
                     fontWeight = if (isCur) FontWeight.Bold else FontWeight.Normal)
            }
        }
    }
}
