# Install Ollama

RigStory Studio uses Ollama only for structured planning. The deterministic editor, character builder, fixtures, and runtime can run without a model.

## Native Setup

1. Install Ollama from `https://ollama.com`.
2. Start Ollama.
3. Pull a model that generally handles JSON schemas well:

```powershell
ollama pull qwen2.5:7b
```

4. Keep the default backend setting unless your Ollama server is elsewhere:

```text
OLLAMA_BASE_URL=http://localhost:11434
```

5. Open **Settings** in the app, select the model, and run **Test model**.

## Docker Compose

Compose defaults `OLLAMA_BASE_URL` to `http://host.docker.internal:11434` so the backend container can reach Ollama running on the host. On Linux, the compose file maps `host.docker.internal` through `host-gateway`.

If model listing works but structured generation fails, try a stronger local model or use the fixture mode to verify the editor workflow independently of model quality.
