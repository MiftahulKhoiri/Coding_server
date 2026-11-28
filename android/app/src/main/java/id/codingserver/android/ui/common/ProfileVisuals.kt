package id.codingserver.android.ui.common

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.UserOut
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Latar profil (di belakang foto). Kunci disimpan di server (users.cover); "" = ikut warna tema. */
val ProfileCovers: List<Pair<String, List<Color>>> = listOf(
    "laut" to listOf(Color(0xFF0F2027), Color(0xFF2C5364), Color(0xFF26C6DA)),
    "senja" to listOf(Color(0xFFFF7E5F), Color(0xFFFEB47B)),
    "hutan" to listOf(Color(0xFF134E5E), Color(0xFF71B280)),
    "anggur" to listOf(Color(0xFF41295A), Color(0xFF2F0743), Color(0xFF8E2DE2)),
    "malam" to listOf(Color(0xFF0F0C29), Color(0xFF302B63), Color(0xFF24243E)),
    "mawar" to listOf(Color(0xFFEE9CA7), Color(0xFFFFDDE1)),
    "aurora" to listOf(Color(0xFF00C9FF), Color(0xFF92FE9D)),
    "batu" to listOf(Color(0xFF3E5151), Color(0xFFDECBA4)),
    "api" to listOf(Color(0xFFF12711), Color(0xFFF5AF19)),
    "es" to listOf(Color(0xFF83A4D4), Color(0xFFB6FBFF)),
)

val CoverNames = mapOf("" to "Tema", "laut" to "Laut", "senja" to "Senja", "hutan" to "Hutan", "anggur" to "Anggur",
                       "malam" to "Malam", "mawar" to "Mawar", "aurora" to "Aurora", "batu" to "Batu", "api" to "Api", "es" to "Es")

/** Kuas latar profil: preset gradasi, warna #RRGGBB, atau [fallback] (warna tema). */
fun coverBrush(cover: String?, fallback: List<Color>): Brush {
    val preset = ProfileCovers.firstOrNull { it.first == cover }?.second
    val colors = preset ?: cover?.takeIf { Regex("^#[0-9A-Fa-f]{6}$").matches(it) }
        ?.let { val c = Color(android.graphics.Color.parseColor(it)); listOf(c, c.copy(alpha = 0.75f)) } ?: fallback
    return if (colors.size == 1) Brush.linearGradient(listOf(colors[0], colors[0]))
           else Brush.linearGradient(colors, start = Offset.Zero, end = Offset(900f, 500f))
}

/** Foto profil layar penuh: cubit untuk memperbesar, geser untuk memindah, ketuk dua kali = reset, ketuk = tutup. */
@Composable
fun AvatarViewer(client: ApiClient, user: UserOut, onDismiss: () -> Unit) {
    var image by remember { mutableStateOf<ImageBitmap?>(null) }
    var failed by remember { mutableStateOf(false) }
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    LaunchedEffect(user.id, user.avatar_version) {
        apiCall { client.api.avatar(user.id).bytes() }.onSuccess { bytes ->
            image = withContext(Dispatchers.Default) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap() }
            if (image == null) failed = true
        }.onFailure { failed = true }
    }
    val state = rememberTransformableState { zoom, pan, _ ->
        scale = (scale * zoom).coerceIn(1f, 6f)
        offset = if (scale == 1f) Offset.Zero else offset + pan
    }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black)
                .pointerInput(Unit) { detectTapGestures(onTap = { onDismiss() }, onDoubleTap = { scale = 1f; offset = Offset.Zero }) },
            contentAlignment = Alignment.Center) {
            val img = image
            when {
                img != null -> Image(img, "Foto profil ${user.shownName}", contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxWidth().transformable(state).graphicsLayer {
                        scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y
                    })
                failed -> Text("Foto tidak bisa dimuat", color = Color.White)
                else -> CircularProgressIndicator()
            }
            Column(Modifier.align(Alignment.BottomCenter).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(user.shownName, color = Color.White)
                Text("@${user.username}", color = Color(0xCCFFFFFF))
            }
        }
    }
}
