from __future__ import annotations

from time import perf_counter

from app.domain.character_builder import CharacterBuilderRequest, build_procedural_character
from app.domain.mesh_skinning import skin_attachment_vertices


def main() -> None:
    result = build_procedural_character(
        CharacterBuilderRequest(name="Mesh Skinning Benchmark", top="jacket", bottom="trousers")
    )
    meshes = [part for part in result.character.attachments if part.kind == "mesh"]
    iterations = 2_000

    started = perf_counter()
    vertex_count = 0
    for _ in range(iterations):
        for mesh in meshes:
            vertex_count += len(skin_attachment_vertices(mesh, result.character.rig))
    elapsed_ms = (perf_counter() - started) * 1000.0

    print(
        "mesh_skinning "
        f"meshes={len(meshes)} iterations={iterations} vertices={vertex_count} "
        f"elapsed_ms={elapsed_ms:.3f} "
        f"us_per_mesh={(elapsed_ms * 1000.0) / (iterations * max(len(meshes), 1)):.3f}"
    )
    print("gpu_path=optional_not_required")


if __name__ == "__main__":
    main()
