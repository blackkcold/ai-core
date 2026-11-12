"""Generate runnable examples without embedding credentials."""
import json
import re
import shlex
from urllib.parse import quote
from .errors import InvalidRequest
from .registry import get_provider


def generate_setup(provider_id: str, *, language="python", model="REPLACE_WITH_MODEL_ID", mode="core") -> dict:
    p = get_provider(provider_id)
    if language not in {"python", "typescript", "swift", "kotlin", "curl"} or mode not in {"core", "native"}:
        raise InvalidRequest("unsupported language or setup mode")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_./:+-]{1,180}", model):
        raise InvalidRequest("invalid model ID")
    body = {"provider": p.id, "model": model, "messages": [{"role": "user", "content": "Hello!"}],
            "max_tokens": 1024}
    if mode == "native":
        if language != "curl" or p.protocol == "catalog-only":
            raise InvalidRequest("native setup examples use curl; this protocol must be supported")
        url = p.base_url.rstrip("/")
        payload = {"model": model, "messages": body["messages"]}
        if p.protocol == "anthropic":
            url += "/messages"
            payload["max_tokens"] = 1024
            headers = ['-H "x-api-key: $' + p.key_env + '"',
                       '-H "anthropic-version: 2023-06-01"']
        elif p.protocol == "gemini":
            url += "/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent"
            payload = {"contents": [{"role": "user", "parts": [{"text": "Hello!"}]}]}
            headers = ['-H "x-goog-api-key: $' + p.key_env + '"']
        elif p.protocol == "ollama":
            url += "/api/chat"
            payload["stream"] = False
            headers = ['-H "Authorization: Bearer $' + p.key_env + '"'] if p.key_env else []
        else:
            url += "/chat/completions"
            headers = ['-H "Authorization: Bearer $' + p.key_env + '"']
        code = ("curl -sS -X POST " + shlex.quote(url) +
                " -H 'Content-Type: application/json' " +
                " ".join(headers) + " --data " + shlex.quote(json.dumps(payload)))
    elif language == "curl":
        code = ("curl -sS -X POST \"$AI_CORE_URL/v1/chat/completions\" "
                "-H \"Authorization: Bearer $AI_CORE_TOKEN\" "
                "-H 'Content-Type: application/json' "
                "--data " + shlex.quote(json.dumps(body)))
    elif language == "python":
        code = (
            "import json, os, urllib.request\n\n"
            "url = os.getenv('AI_CORE_URL', 'http://127.0.0.1:8765') + '/v1/chat/completions'\n"
            "payload = " + repr(body) + "\n"
            "request = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',\n"
            "    headers={'Content-Type': 'application/json',\n"
            "             'Authorization': 'Bearer ' + os.getenv('AI_CORE_TOKEN', '')})\n"
            "with urllib.request.urlopen(request, timeout=90) as response:\n"
            "    print(json.load(response))\n")
    elif language == "typescript":
        code = (
            "const response = await fetch((process.env.AI_CORE_URL ?? 'http://127.0.0.1:8765') + '/v1/chat/completions', {\n"
            "  method: 'POST',\n"
            "  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (process.env.AI_CORE_TOKEN ?? '') },\n"
            "  body: JSON.stringify(" + json.dumps(body, ensure_ascii=False) + "),\n"
            "});\n"
            "if (!response.ok) throw new Error('AI Core HTTP ' + response.status);\n"
            "console.log(await response.json());\n")
    elif language == "kotlin":
        code = (
            "import dev.aicore.client.AICoreClient\n"
            "import org.json.JSONArray\n"
            "import org.json.JSONObject\n\n"
            "val client = AICoreClient(baseUrl = System.getenv(\"AI_CORE_URL\")"
            " ?: \"http://127.0.0.1:8765\", token = System.getenv(\"AI_CORE_TOKEN\") ?: \"\")\n"
            "println(client.chat(provider = " + json.dumps(p.id) + ", model = " + json.dumps(model)
            + ", messages = JSONArray().put(JSONObject().put(\"role\", \"user\").put(\"content\", \"Hello!\"))))\n"
        )
    else:
        code = (
            "import Foundation\n\n"
            "func sendAIRequest() async throws -> Data {\n"
            "    let env = ProcessInfo.processInfo.environment\n"
            "    let base = env[\"AI_CORE_URL\"] ?? \"http://127.0.0.1:8765\"\n"
            "    var request = URLRequest(url: URL(string: base + \"/v1/chat/completions\")!)\n"
            "    request.httpMethod = \"POST\"\n"
            "    request.setValue(\"application/json\", forHTTPHeaderField: \"Content-Type\")\n"
            "    request.setValue(\"Bearer \" + (env[\"AI_CORE_TOKEN\"] ?? \"\"), forHTTPHeaderField: \"Authorization\")\n"
            "    request.httpBody = try JSONSerialization.data(withJSONObject: [\n"
            "        \"provider\": " + json.dumps(p.id) + ", \"model\": " + json.dumps(model) + ", \"max_tokens\": 1024,\n"
            "        \"messages\": [[\"role\": \"user\", \"content\": \"Hello!\"]]\n"
            "    ])\n"
            "    let (data, response) = try await URLSession.shared.data(for: request)\n"
            "    guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }\n"
            "    return data\n"
            "}\n")
    return {"provider": p.id, "language": language, "mode": mode,
            "protocol": p.protocol, "base_url": p.base_url, "models_url": p.models_url,
            "key_env": p.key_env, "docs": p.docs, "pricing": p.pricing,
            "code": code, "note": "Model access and billing depend on the provider account; never embed API keys."}
