package id.codingserver.android

import id.codingserver.android.ui.editor.EditorColorPresets
import id.codingserver.android.ui.theme.AccentPalette
import id.codingserver.android.ui.theme.ThemeMode
import id.codingserver.android.ui.theme.colorSchemeFor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ThemeTest {
    @Test fun keysUniqueAndRoundTrip() {
        assertEquals(AccentPalette.entries.size, AccentPalette.entries.map { it.key }.toSet().size)
        AccentPalette.entries.forEach { assertEquals(it, AccentPalette.fromKey(it.key)) }
        ThemeMode.entries.forEach { assertEquals(it, ThemeMode.fromKey(it.key)) }
    }

    @Test fun unknownKeysFallBackToDefaults() {
        assertEquals(AccentPalette.BLUE, AccentPalette.fromKey("tidak-ada"))
        assertEquals(AccentPalette.BLUE, AccentPalette.fromKey(null))
        assertEquals(ThemeMode.DARK, ThemeMode.fromKey(null))
    }

    @Test fun amoledMakesDarkBackgroundBlack() {
        val s = colorSchemeFor(AccentPalette.GREEN, dark = true, amoled = true)
        assertEquals(0f, s.background.red + s.background.green + s.background.blue, 0f)
        assertEquals(AccentPalette.GREEN.darkPrimary, s.primary)
        assertEquals(AccentPalette.GREEN.lightPrimary, colorSchemeFor(AccentPalette.GREEN, dark = false, amoled = true).primary)
    }

    @Test fun editorPresetsAreValidHex() {
        val hex = Regex("^#[0-9A-Fa-f]{6}$")
        EditorColorPresets.forEach { assertTrue(it.name, hex.matches(it.text) && hex.matches(it.background)) }
    }
}
