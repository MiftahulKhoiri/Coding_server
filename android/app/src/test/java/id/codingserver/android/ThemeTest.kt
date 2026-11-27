package id.codingserver.android

import id.codingserver.android.ui.editor.EditorColorPresets
import id.codingserver.android.ui.theme.AccentPalette
import id.codingserver.android.ui.theme.BackgroundTone
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

    @Test fun backgroundToneChangesSurfaces() {
        BackgroundTone.entries.forEach { assertEquals(it, BackgroundTone.fromKey(it.key)) }
        assertEquals(BackgroundTone.NEUTRAL, BackgroundTone.fromKey(null))
        val navy = colorSchemeFor(AccentPalette.BLUE, dark = true, amoled = false, background = BackgroundTone.NAVY)
        assertEquals(BackgroundTone.NAVY.darkBg, navy.background)
        assertEquals(BackgroundTone.NAVY.darkSurface, navy.surface)
        val light = colorSchemeFor(AccentPalette.BLUE, dark = false, amoled = false, background = BackgroundTone.SEPIA)
        assertEquals(BackgroundTone.SEPIA.lightBg, light.background)
        // AMOLED tetap hitam murni meski latar dipilih
        val am = colorSchemeFor(AccentPalette.BLUE, dark = true, amoled = true, background = BackgroundTone.FOREST)
        assertEquals(0f, am.background.red + am.background.green + am.background.blue, 0f)
    }

    @Test fun editorPresetsAreValidHex() {
        val hex = Regex("^#[0-9A-Fa-f]{6}$")
        EditorColorPresets.forEach { assertTrue(it.name, hex.matches(it.text) && hex.matches(it.background)) }
    }
}
