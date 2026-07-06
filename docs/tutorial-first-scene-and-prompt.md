# Tutorial: First Scene And Prompt

1. Create or open a project containing a generated or sample character.
2. Open **Scenes**.
3. Use the scene demo or add a floor, a chair object, a `seat` anchor, and a `sit` affordance.
4. Confirm the scene snapshot panel shows compact semantic data rather than SVG paths or image payloads.
5. Open **Motion**.
6. Enter a prompt such as:

```text
Walk to the chair, sit down, and wave.
```

7. Use a live Ollama model or the fixture path when working offline.
8. Inspect the generated action cards, warnings, and JSON preview.
9. Compile the approved plan into an editable clip.
10. Open the rig/timeline view and scrub the result.

Expected result: the model creates a semantic `MotionPlan`; the deterministic compiler creates the editable animation clip and validation metrics.
