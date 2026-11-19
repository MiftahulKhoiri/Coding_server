package id.codingserver.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.sp

val Mono = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 13.sp)
val OkGreen = Color(0xFF43A047)
val WarnAmber = Color(0xFFFFA000)
val ErrRed = Color(0xFFE53935)

private val Dark = darkColorScheme(
    primary = Color(0xFF64B5F6), secondary = Color(0xFF80CBC4), tertiary = Color(0xFFFFB74D),
    background = Color(0xFF121212), surface = Color(0xFF1B1B1F),
)
private val Light = lightColorScheme(primary = Color(0xFF1565C0), secondary = Color(0xFF00897B), tertiary = Color(0xFFEF6C00))

@Composable
fun CodingServerTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, typography = Typography(), content = content)
}
