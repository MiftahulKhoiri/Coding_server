package id.codingserver.android

import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.Job
import id.codingserver.android.data.api.normalizeBaseUrl
import id.codingserver.android.data.update.AppUpdater
import id.codingserver.android.ui.editor.DiagnosticParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class UnitTests {
    @Test fun normalizeUrl() {
        assertEquals("http://192.168.1.5:8800/", normalizeBaseUrl("192.168.1.5"))
        assertEquals("http://192.168.1.5:9000/", normalizeBaseUrl("http://192.168.1.5:9000/"))
        assertEquals("https://pi.example.com/", normalizeBaseUrl("https://pi.example.com"))
    }

    @Test fun parseBuildNumber() {
        assertEquals(12, AppUpdater.parseBuildNumber("Coding Server Android (build #12)"))
        assertEquals(null, AppUpdater.parseBuildNumber("tanpa nomor"))
    }

    @Test fun parseGccErrors() {
        val out = "main.c:3:5: error: expected ';' before 'return'\nmain.c:7:1: warning: unused variable 'x'\n"
        val d = DiagnosticParser.parse(out, "src/main.c")
        assertEquals(2, d.size)
        assertEquals(3, d[0].line); assertEquals(5, d[0].column); assertEquals("error", d[0].severity)
        assertEquals("warning", d[1].severity)
    }

    @Test fun parsePythonTraceback() {
        val out = "Traceback (most recent call last):\n  File \"/w/p/main.py\", line 4, in <module>\n    x = 1/0\nZeroDivisionError: division by zero\n"
        val d = DiagnosticParser.parse(out, "main.py")
        assertEquals(4, d.single().line)
        assertTrue(d.single().message.contains("ZeroDivisionError"))
    }

    @Test fun parseJavacAndGo() {
        assertEquals(2, DiagnosticParser.parse("Main.java:2: error: ';' expected", "Main.java").single().line)
        assertEquals(9, DiagnosticParser.parse("./main.go:9:2: undefined: foo", "main.go").single().line)
    }

    @Test fun decodeJobFromBackend() {
        val raw = """{"process_id":"abc","project_id":"p","user_id":1,"action":"run","language":"python","file":"main.py",
            "status":"COMPLETED","exit_code":0,"command":[["python3","-u","main.py"]],"error":"","created_at":1.5,
            "start_time":1.6,"end_time":2.0,"duration":0.4,"truncated":false,"preview_path":null,"stdout":"hi\n","stderr":"","extra":1}"""
        val j = ApiJson.decodeFromString(Job.serializer(), raw)
        assertTrue(j.finished)
        assertEquals("hi\n", j.stdout)
    }
}
