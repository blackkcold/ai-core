package dev.aicore.client

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Android/JVM REST + SSE client. All methods block; call on a worker dispatcher,
 * never Android's UI thread. Configure a reachable TLS gateway for devices.
 */
class AICoreClient(
    private val baseUrl: String = "http://127.0.0.1:8765",
    private val token: String = "",
    private val project: String? = null
) {
    private fun connection(path: String, streaming: Boolean = false): HttpURLConnection {
        require(path.startsWith("/v1/")) { "unsupported endpoint" }
        return (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10000
            readTimeout = 90000
            setRequestProperty("Accept", if (streaming) "text/event-stream" else "application/json")
            if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer " + token)
            if (project != null) setRequestProperty("X-AI-Core-Project", project)
        }
    }

    private fun call(path: String, body: JSONObject? = null): JSONObject {
        val conn = connection(path)
        try {
            conn.requestMethod = if (body == null) "GET" else "POST"
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            if (conn.responseCode !in 200..299) error("AI Core HTTP " + conn.responseCode)
            return JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        } finally {
            conn.disconnect()
        }
    }

    private fun query(value: String): String = URLEncoder.encode(value, "UTF-8")

    fun providers(): JSONObject = call("/v1/providers")
    fun searchProviders(): JSONObject = call("/v1/search/providers")
    fun freeModels(): JSONObject = call("/v1/free/models")
    fun models(provider: String = "auto", refresh: Boolean = false): JSONObject =
        call("/v1/models?provider=" + query(provider) + "&refresh=" + if (refresh) "1" else "0")

    fun search(query: String, limit: Int = 6, category: String = "general",
               language: String? = null, recency: String? = null): JSONObject {
        val body = JSONObject().put("query", query).put("limit", limit).put("category", category)
        language?.let { body.put("language", it) }
        recency?.let { body.put("recency", it) }
        return call("/v1/tools/web_search", body)
    }

    fun fetchPage(url: String): JSONObject =
        call("/v1/tools/web_fetch", JSONObject().put("url", url))

    fun chat(provider: String, model: String, messages: JSONArray): JSONObject =
        call("/v1/chat/completions", JSONObject().put("provider", provider)
            .put("model", model).put("messages", messages))

    fun chat(messages: JSONArray): JSONObject = chat("auto", "auto", messages)
    fun usage(): JSONObject = call("/v1/usage")

    /** Calls onEvent for each parsed SSE JSON object; run in a background thread. */
    fun streamChat(provider: String, model: String, messages: JSONArray,
                   onEvent: (JSONObject) -> Unit) {
        val conn = connection("/v1/chat/completions", streaming = true)
        try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            val payload = JSONObject().put("provider", provider).put("model", model)
                .put("messages", messages).put("stream", true)
            conn.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode !in 200..299) error("AI Core stream HTTP " + conn.responseCode)
            val parts = mutableListOf<String>()
            conn.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                while (true) {
                    val line = reader.readLine() ?: break
                    if (Thread.currentThread().isInterrupted) break
                    if (line.startsWith("data:")) {
                        parts.add(line.removePrefix("data:").trimStart())
                    } else if (line.isEmpty() && parts.isNotEmpty()) {
                        val event = parts.joinToString("\n")
                        parts.clear()
                        if (event == "[DONE]") break
                        val parsed = JSONObject(event)
                        if (parsed.has("error")) error("AI Core upstream stream error")
                        onEvent(parsed)
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
    }

    fun streamChat(messages: JSONArray, onEvent: (JSONObject) -> Unit) =
        streamChat("auto", "auto", messages, onEvent)
}
