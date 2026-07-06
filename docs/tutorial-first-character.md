# Tutorial: First Character

1. Start the app with Docker Compose or the native scripts in `docs/development.md`.
2. Open `http://localhost:5173`.
3. Select **Characters**.
4. Choose a preset or adjust the presentation, proportions, palette, hair, face, clothes, and style fields.
5. Inspect the rig preview. Use **Region** and **Regenerate** to update one visual section deterministically.
6. Select an Ollama model only if you want the model to fill a `CharacterBlueprint`; the procedural builder works without Ollama.
7. Click **Save**.
8. Open **Rig Editor** to select bones, inspect world transforms, and test manual posing.

Expected result: a saved vector character with a canonical editable rig, visual attachments, builder diagnostics, and no dependency on unvalidated model output.
