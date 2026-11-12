package dev.aicore.client

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Minimal Android/JVM REST client. Run on a background dispatcher, never the UI thread. */
class AICoreClient(
    private val baseUrl: String = "http://127.0.0.1:8765",
    private val token: String = "",
    private val project: String? = null
) {
    private fun call(path: String, body: JSONObject? = null): JSONObject {
        require(path.startsWith("/v1/")) { "unsupported endpoint" }
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        connection.requestMethod = if (body == null) "GET" else "POST"
        connection.connectTimeout = 10000
        connection.readTimeout = 90000
        connection.setRequestProperty("Accept", "application/json")
        if (token.isNotBlank()) connection.setRequestProperty("Authorization", "Bearer " + token)
        if (project != null) connection.setRequestProperty("X-AI-Core-Project", project)
        try {
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            if (connection.responseCode !in 200..299) error("AI Core HTTP " + connection.responseCode)
            return JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }

    fun providers(): JSONObject = call("/v1/providers")
    fun search(query: String, limit: Int = 6): JSONObject =
        call("/v1/tools/web_search", JSONObject().put("query", query).put("limit", limit))
    fun chat(provider: String, model: String, messages: JSONArray): JSONObject =
        call("/v1/chat/completions", JSONObject().put("provider", provider)
            .put("model", model).put("messages", messages))
    fun usage(): JSONObject = call("/v1/usage")
}
