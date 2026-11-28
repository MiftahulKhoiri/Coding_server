package id.codingserver.android

import id.codingserver.android.data.api.AIProposalItem
import id.codingserver.android.data.api.AgentEvents
import id.codingserver.android.data.api.AgentTask
import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.Job
import id.codingserver.android.data.api.normalizeBaseUrl
import id.codingserver.android.data.update.AppUpdater
import id.codingserver.android.ui.ai.splitMarkdown
import id.codingserver.android.ui.editor.DiagnosticParser
import id.codingserver.android.ui.editor.quickOpenFilter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class UnitTests {
    @Test fun quickOpenRanksFileNameFirst() {
        val files = listOf("docs/main_notes.md", "src/app/main.py", "src/domain/util.py", "main.cpp", "tests/test_main.py")
        val r = quickOpenFilter(files, "main")
        assertEquals(listOf("main.cpp", "src/app/main.py", "docs/main_notes.md", "tests/test_main.py", "src/domain/util.py"), r)  // terakhir: fuzzy "do-main"
        assertEquals(listOf("src/domain/util.py"), quickOpenFilter(files, "sdu"))  // fuzzy: s…d…u berurutan di path
        assertEquals(files, quickOpenFilter(files, " "))
    }

    @Test fun decodeAgentTaskAndEvents() {
        val json = """{"id":"abc","project_id":"p","title":"t","description":"d","status":"COMPLETED","stage":"COMPLETED",
            "progress":1.0,"current_op":"","model":"coder","error":"","max_steps":30,"steps_used":5,"created_at":1.0,
            "started_at":1.5,"updated_at":2.0,"finished_at":2.0,"duration":0.5,"auto_apply":false,"pending_proposals":0,
            "plan":[{"id":"1","description":"perbaiki","files":["a.py"],"depends_on":[],"risk":"MEDIUM","verification":"run_tests","status":"done"}],
            "report":{"verified":{"proposals":[],"files_changed":["a.py"],"files_pending":[],"runs":[{"kind":"test","target":"pytest",
            "status":"COMPLETED","exit_code":0,"process_id":"x"}],"tests_passed":1,"tests_failed":0,"steps_used":5,"plan":[]},
            "ai_generated":{"summary":"ok","limitations":null,"remaining":null},"note":"n"},"extra_field":1}"""
        val t = ApiJson.decodeFromString<AgentTask>(json)
        assertEquals("COMPLETED", t.status)
        assertEquals(listOf("a.py"), t.report!!.verified.files_changed)
        assertEquals(1, t.report!!.verified.tests_passed)
        assertEquals("done", t.plan.single().status)
        val ev = ApiJson.decodeFromString<AgentEvents>(
            """{"events":[{"id":3,"ts":1.0,"kind":"tool_call","data":{"tool":"read_file","args":{"path":"a.py"}}}]}""")
        assertEquals("tool_call", ev.events.single().kind)
        val p = ApiJson.decodeFromString<AIProposalItem>(
            """{"id":1,"path":"run.sh","risk":"HIGH","risk_reasons":["skrip shell"],"task_id":"abc","new_file":true}""")
        assertEquals("HIGH", p.risk)
        assertEquals("abc", p.task_id)
    }

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

    @Test fun markdownCodeBlocks() {
        val parts = splitMarkdown("Ini kode:\n```python\nprint(1)\n```\nSelesai")
        assertEquals(3, parts.size)
        assertTrue(parts[1].code)
        assertEquals("python", parts[1].lang)
        assertEquals("print(1)", parts[1].text)
        // blok kode yang belum ditutup (masih streaming) tetap jadi kode
        assertTrue(splitMarkdown("```js\nlet a").last().code)
    }
}
