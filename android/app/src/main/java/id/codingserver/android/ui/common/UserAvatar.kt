package id.codingserver.android.ui.common

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.media.ExifInterface
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.UserOut
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

/** Cache foto profil di memori: kunci = server|userId|versi, jadi foto baru otomatis termuat ulang. */
private object AvatarCache {
    val images = LruCache<String, ImageBitmap>(32)
}

/**
 * Foto profil bulat. Bila pengguna belum punya foto (atau gagal dimuat), tampil huruf awal namanya.
 * [root] memberi warna berbeda untuk admin utama.
 */
@Composable
fun UserAvatar(client: ApiClient?, user: UserOut?, size: Dp = 48.dp, modifier: Modifier = Modifier) {
    val version = user?.avatar_version
    val key = if (client != null && user != null && version != null) "${client.baseUrl}|${user.id}|$version" else null
    var image by remember(key) { mutableStateOf(key?.let { AvatarCache.images.get(it) }) }

    LaunchedEffect(key) {
        if (key == null || image != null || client == null || user == null) return@LaunchedEffect
        apiCall { client.api.avatar(user.id).bytes() }.onSuccess { bytes ->
            val bmp = withContext(Dispatchers.Default) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
            if (bmp != null) {
                val img = bmp.asImageBitmap()
                AvatarCache.images.put(key, img)
                image = img
            }
        }
    }

    val root = user?.is_root == true
    val ring = if (root) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.primary
    val img = image
    if (img != null) {
        Image(img, contentDescription = "Foto profil ${user?.shownName ?: ""}", contentScale = ContentScale.Crop,
            modifier = modifier.size(size).clip(CircleShape).border(2.dp, ring, CircleShape))
    } else {
        val bg = if (root) MaterialTheme.colorScheme.tertiaryContainer else MaterialTheme.colorScheme.primaryContainer
        Box(modifier.size(size).background(bg, CircleShape), contentAlignment = Alignment.Center) {
            Text((user?.shownName ?: "?").trim().take(1).uppercase().ifBlank { "?" },
                fontSize = (size.value * 0.42f).sp, fontWeight = FontWeight.Bold,
                color = if (root) MaterialTheme.colorScheme.onTertiaryContainer else MaterialTheme.colorScheme.onPrimaryContainer)
        }
    }
}

/**
 * Baca gambar dari galeri, putar sesuai EXIF, potong persegi di tengah, perkecil ke [target] px, lalu JPEG.
 * Hasil ±30–80 KB sehingga ringan untuk server Pi dan cepat dimuat.
 */
suspend fun prepareAvatar(context: Context, uri: Uri, target: Int = 512): ByteArray = withContext(Dispatchers.IO) {
    val cr = context.contentResolver
    // inJustDecodeBounds: decodeStream SELALU mengembalikan null; ukuran dibaca dari bounds.outWidth/outHeight.
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    val stream = cr.openInputStream(uri) ?: error("Tidak bisa membuka gambar")
    stream.use { BitmapFactory.decodeStream(it, null, bounds) }
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) error("Format gambar tidak didukung")
    var sample = 1
    while (minOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= target) sample *= 2
    val decoded = cr.openInputStream(uri)?.use {
        BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
    } ?: error("Format gambar tidak didukung")
    val rotation = runCatching {
        cr.openInputStream(uri)?.use {
            when (ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> 0f
            }
        } ?: 0f
    }.getOrDefault(0f)
    val side = minOf(decoded.width, decoded.height)
    val m = Matrix().apply {
        val scale = target.toFloat() / side
        if (scale < 1f) postScale(scale, scale)
        if (rotation != 0f) postRotate(rotation)
    }
    val square = Bitmap.createBitmap(decoded, (decoded.width - side) / 2, (decoded.height - side) / 2, side, side, m, true)
    ByteArrayOutputStream().use { out ->
        square.compress(Bitmap.CompressFormat.JPEG, 85, out)
        out.toByteArray()
    }
}
