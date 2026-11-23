package id.codingserver.android.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.sp

val Mono = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 13.sp)
val OkGreen = Color(0xFF43A047)
val WarnAmber = Color(0xFFFFA000)
val ErrRed = Color(0xFFE53935)

/** Mode terang/gelap aplikasi. */
enum class ThemeMode(val key: String, val label: String) {
    SYSTEM("system", "Ikuti sistem"), DARK("dark", "Gelap"), LIGHT("light", "Terang");
    companion object { fun fromKey(k: String?) = entries.firstOrNull { it.key == k } ?: DARK }
}

/**
 * Palet warna aksen. Warna untuk mode gelap dibuat lebih terang (kontras di latar gelap),
 * warna mode terang lebih pekat (kontras di latar putih).
 */
enum class AccentPalette(
    val key: String,
    val label: String,
    val darkPrimary: Color, val darkSecondary: Color, val darkTertiary: Color,
    val lightPrimary: Color, val lightSecondary: Color, val lightTertiary: Color,
) {
    BLUE("blue", "Biru", Color(0xFF64B5F6), Color(0xFF80CBC4), Color(0xFFFFB74D), Color(0xFF1565C0), Color(0xFF00897B), Color(0xFFEF6C00)),
    TEAL("teal", "Teal", Color(0xFF4DD0E1), Color(0xFF80CBC4), Color(0xFFFFD54F), Color(0xFF00838F), Color(0xFF00695C), Color(0xFFF9A825)),
    GREEN("green", "Hijau", Color(0xFF81C784), Color(0xFFAED581), Color(0xFF4FC3F7), Color(0xFF2E7D32), Color(0xFF558B2F), Color(0xFF0277BD)),
    PURPLE("purple", "Ungu", Color(0xFFB39DDB), Color(0xFFF48FB1), Color(0xFF80DEEA), Color(0xFF5E35B1), Color(0xFFAD1457), Color(0xFF00838F)),
    INDIGO("indigo", "Nila", Color(0xFF9FA8DA), Color(0xFF90CAF9), Color(0xFFFFCC80), Color(0xFF3949AB), Color(0xFF1E88E5), Color(0xFFE65100)),
    ORANGE("orange", "Oranye", Color(0xFFFFB74D), Color(0xFFFFD54F), Color(0xFF81D4FA), Color(0xFFE65100), Color(0xFFF57F17), Color(0xFF0277BD)),
    RED("red", "Merah", Color(0xFFEF9A9A), Color(0xFFFFAB91), Color(0xFF90CAF9), Color(0xFFC62828), Color(0xFFD84315), Color(0xFF1565C0)),
    PINK("pink", "Merah muda", Color(0xFFF48FB1), Color(0xFFCE93D8), Color(0xFF80CBC4), Color(0xFFC2185B), Color(0xFF8E24AA), Color(0xFF00897B)),
    AMBER("amber", "Kuning", Color(0xFFFFE082), Color(0xFFFFCC80), Color(0xFF80DEEA), Color(0xFFFF8F00), Color(0xFFEF6C00), Color(0xFF00838F)),
    GRAY("gray", "Abu-abu", Color(0xFFB0BEC5), Color(0xFF90A4AE), Color(0xFFFFCC80), Color(0xFF455A64), Color(0xFF607D8B), Color(0xFFE65100)),
    /** Material You: warna diambil dari wallpaper HP (Android 12+), selain itu jatuh ke Biru. */
    DYNAMIC("dynamic", "Dinamis", Color(0xFF64B5F6), Color(0xFF80CBC4), Color(0xFFFFB74D), Color(0xFF1565C0), Color(0xFF00897B), Color(0xFFEF6C00));

    companion object {
        fun fromKey(k: String?) = entries.firstOrNull { it.key == k } ?: BLUE
        val dynamicSupported get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    }
}

/** Preferensi tampilan aplikasi (disimpan di DataStore). */
data class AppTheme(
    val mode: ThemeMode = ThemeMode.DARK,
    val accent: AccentPalette = AccentPalette.BLUE,
    /** Latar hitam pekat di mode gelap — hemat baterai di layar AMOLED. */
    val amoled: Boolean = false,
)

private fun onColor(c: Color): Color = if (c.luminanceApprox() > 0.5f) Color(0xFF111111) else Color.White
private fun Color.luminanceApprox() = 0.2126f * red + 0.7152f * green + 0.0722f * blue

/** Bangun ColorScheme statis untuk palet (dipakai juga oleh unit test). */
fun colorSchemeFor(accent: AccentPalette, dark: Boolean, amoled: Boolean): ColorScheme =
    if (dark) {
        val bg = if (amoled) Color.Black else Color(0xFF121212)
        val surface = if (amoled) Color(0xFF0A0A0A) else Color(0xFF1B1B1F)
        darkColorScheme(
            primary = accent.darkPrimary, onPrimary = onColor(accent.darkPrimary),
            secondary = accent.darkSecondary, onSecondary = onColor(accent.darkSecondary),
            tertiary = accent.darkTertiary, onTertiary = onColor(accent.darkTertiary),
            background = bg, surface = surface,
        )
    } else {
        lightColorScheme(
            primary = accent.lightPrimary, onPrimary = onColor(accent.lightPrimary),
            secondary = accent.lightSecondary, onSecondary = onColor(accent.lightSecondary),
            tertiary = accent.lightTertiary, onTertiary = onColor(accent.lightTertiary),
        )
    }

@Composable
fun isAppDark(theme: AppTheme): Boolean = when (theme.mode) {
    ThemeMode.SYSTEM -> isSystemInDarkTheme()
    ThemeMode.DARK -> true
    ThemeMode.LIGHT -> false
}

@Composable
fun CodingServerTheme(theme: AppTheme = AppTheme(), content: @Composable () -> Unit) {
    val dark = isAppDark(theme)
    val scheme = if (theme.accent == AccentPalette.DYNAMIC && AccentPalette.dynamicSupported) {
        val ctx = LocalContext.current
        if (dark) dynamicDarkColorScheme(ctx).let {
            if (theme.amoled) it.copy(background = Color.Black, surface = Color(0xFF0A0A0A)) else it
        } else dynamicLightColorScheme(ctx)
    } else colorSchemeFor(theme.accent, dark, theme.amoled)
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
}
