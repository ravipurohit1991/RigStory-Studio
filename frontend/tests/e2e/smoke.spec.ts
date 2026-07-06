import { expect, test } from "@playwright/test";

const healthPayload = {
  status: "healthy",
  application: { status: "healthy", detail: "app" },
  database: { status: "healthy", detail: "db" },
  assets: { status: "healthy", detail: "assets" },
  ollama: {
    status: "unavailable",
    base_url: "http://localhost:11434",
    detail: "connection refused"
  }
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as {
        document?: { project?: { id?: string; name?: string } };
      };
      await route.fulfill({
        json: {
          document: payload.document,
          revision: "rev_e2e_builder_save"
        }
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ json: healthPayload });
  });
  await page.route("**/api/v1/settings", async (route) => {
    await route.fulfill({
      json: {
        app_name: "RigStory Studio",
        app_version: "0.1.0",
        environment: "local",
        api_base_path: "/api/v1",
        asset_store_path: "./data",
        ollama_base_url: "http://localhost:11434",
        ollama_generation_timeout_seconds: 120,
        ollama_keep_alive: "10m"
      }
    });
  });
  // Default: no local models. Individual tests may override this route.
  await page.route("**/api/v1/ollama/models", async (route) => {
    await route.fulfill({
      json: { available: false, base_url: "http://localhost:11434", models: [], detail: "offline" }
    });
  });
});

test("builds and saves a deterministic procedural character", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("tab", { name: /characters/i }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: /character builder/i })
  ).toBeVisible();

  const canvas = page.locator("canvas.rig-stage-canvas");
  await expect(canvas).toBeVisible();
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox?.width ?? 0).toBeGreaterThan(300);
  expect(canvasBox?.height ?? 0).toBeGreaterThan(300);

  await page.getByLabel("Preset").selectOption("1");
  await expect(page.getByLabel("Name")).toHaveValue("Jon Cutout");

  await page.getByLabel("Region", { exact: true }).selectOption("face");
  await page.getByRole("button", { name: /regenerate/i }).click();

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/saved jon cutout character/i)).toBeVisible();
});

test("generates a character from a prompt with a mocked Ollama model", async ({ page }) => {
  const generation = {
    character_id: "char_ai_e2e",
    record_id: "gen_ai_e2e",
    revision: "rev_after",
    status: "succeeded",
    model_name: "mock-model",
    blueprint: {
      schema_version: "1.0",
      character_name: "Nova",
      presentation: "neutral",
      age_category: "adult",
      style: { family: "flat_vector", outline_weight: 2, detail_level: "medium", symmetry: 0.9 },
      warnings: []
    },
    request: {
      name: "Nova",
      presentation: "neutral",
      age_category: "adult",
      height: "average",
      build: "average",
      proportions: {
        shoulder_width: 1,
        torso_length: 1,
        waist_width: 1,
        hip_width: 1,
        arm_length: 1,
        leg_length: 1,
        head_size: 1,
        asymmetry: 0
      },
      palette: {
        skin: "#c98f62",
        hair: "#3d2a1e",
        top: "#2f6f73",
        bottom: "#2f3a56",
        shoes: "#2b2b2b",
        accent: "#f0d36b"
      },
      hair_style: "short",
      face_shape: "oval",
      top: "tshirt",
      bottom: "trousers",
      footwear: "shoes",
      outerwear: "none",
      style: "flat_vector"
    },
    provenance: [{ field: "name", source: "model", model_value: "Nova" }],
    builder_diagnostics: [],
    warnings: ["Used default footwear"]
  };
  const job = {
    id: "job_ai_e2e",
    kind: "character_generation",
    state: "succeeded",
    created_at: "2026-07-04T00:00:00Z",
    updated_at: "2026-07-04T00:00:01Z",
    progress: [],
    result: generation,
    retryable: false
  };

  await page.route("**/api/v1/ollama/models", async (route) => {
    await route.fulfill({
      json: { available: true, base_url: "http://localhost:11434", models: [{ name: "mock-model" }] }
    });
  });
  await page.route("**/characters/generate", async (route) => {
    await route.fulfill({ status: 202, json: job });
  });
  await page.route("**/api/v1/jobs/**", async (route) => {
    await route.fulfill({ json: job });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: /characters/i }).click();

  const generateButton = page.getByRole("button", { name: /generate with ai/i });
  await expect(generateButton).toBeEnabled();
  await generateButton.click();

  await expect(page.getByText(/Blueprint · Nova/i)).toBeVisible();
  await expect(page.getByText(/Used default footwear/i)).toBeVisible();
});

test("loads the shell and reports Ollama separately", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("tab", { name: /projects/i })).toBeVisible();
  await expect(page.getByRole("tab", { name: /player/i })).toBeVisible();
  await expect(page.getByText("No projects yet.")).toBeVisible();

  await page.getByRole("tab", { name: /settings/i }).click();
  await expect(page.getByText("Ollama unavailable")).toBeVisible();

  await page.getByRole("tab", { name: /health/i }).click();
  await expect(page.getByText("Application", { exact: true })).toBeVisible();
  await expect(page.getByText("Ollama", { exact: true })).toBeVisible();
  await expect(page.getByText("unavailable", { exact: true })).toBeVisible();
});

test("opens a semantic scene snapshot and compiles deterministic motion", async ({ page }) => {
  const scene = {
    id: "scene_demo_room",
    name: "Demo Room",
    world_bounds: [-5, -1, 7, 5],
    ground_y: 0,
    actors: [
      {
        id: "actor_mira",
        character_id: "char_biped_alpha",
        display_name: "Mira",
        root_transform: { position: [-3.5, 0], rotation_deg: 0, scale: [1, 1] },
        facing: "right",
        state: "standing"
      }
    ],
    objects: [
      {
        id: "floor_main",
        name: "Floor",
        kind: "floor",
        transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        bounds: [-5, -0.25, 7, 0],
        visual: { type: "rectangle", fill: "#d8dee9", opacity: 1 },
        colliders: [{ type: "box", center: [1, -0.125], size: [12, 0.25], rotation_deg: 0 }],
        anchors: [],
        affordances: [],
        collision_layer: "ground",
        collision_mask: ["default"],
        body_type: "static",
        visible: true,
        locked: false,
        walkable: true,
        blocked: false
      },
      {
        id: "chair_main",
        name: "Chair",
        kind: "chair",
        transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        bounds: [2, 0, 3, 1.4],
        visual: { type: "rectangle", fill: "#b7c7a3", opacity: 1 },
        colliders: [{ type: "box", center: [2.5, 0.45], size: [1, 0.9], rotation_deg: 0 }],
        anchors: [{ id: "seat", position: [2.5, 0.55], rotation_deg: 0 }],
        affordances: [{ type: "sit", anchor_id: "seat" }],
        collision_layer: "default",
        collision_mask: ["default"],
        body_type: "static",
        visible: true,
        locked: false,
        walkable: false,
        blocked: false
      }
    ]
  };
  const project = {
    format: "rigstory-project",
    schema_version: "0.4.0",
    engine_version: "0.1.0",
    project: { id: "project_scene_demo", name: "Scene Demo" },
    characters: [{ id: "char_biped_alpha", name: "Mira", rig: { id: "rig_demo", name: "Rig", bones: [] }, attachments: [] }],
    scenes: [scene],
    clips: [],
    motion_plans: [],
    generation_records: [],
    asset_manifest: []
  };

  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: [{ id: "project_scene_demo", name: "Scene Demo", revision: "rev_scene" }]
      });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/v1/projects/project_scene_demo", async (route) => {
    await route.fulfill({ json: { document: project, revision: "rev_scene" } });
  });
  await page.route("**/api/v1/scenes/scene_demo_room/snapshot", async (route) => {
    await route.fulfill({
      json: {
        byte_length: 240,
        canonical_json: '{"scene_id":"scene_demo_room","walkable_regions":["floor_main"]}',
        snapshot: {
          schema_version: "1.0.0",
          scene_id: "scene_demo_room",
          scene_name: "Demo Room",
          world_bounds: [-5, -1, 7, 5],
          coordinate_system: "Y-up, counterclockwise degrees",
          actors: [],
          objects: [],
          walkable_regions: ["floor_main"],
          blocked_regions: [],
          relations: [],
          reachability: []
        }
      }
    });
  });
  await page.route("**/api/v1/scenes/scene_demo_room/validate", async (route) => {
    await route.fulfill({ json: { issues: [] } });
  });
  await page.route("**/api/v1/motion/demo/compile", async (route) => {
    await route.fulfill({
      json: {
        engine_version: "0.1.0",
        clip: {
          id: "clip_demo_walk_sit_wave",
          scene_id: "scene_demo_room",
          name: "Walk, sit, wave",
          duration: 4.2,
          loop: false,
          loop_range: null,
          tracks: [
            {
              type: "root_translation",
              id: "track_mira_root",
              actor_id: "actor_mira",
              keyframes: []
            }
          ],
          events: [],
          markers: []
        },
        report: {
          clip_id: "clip_demo_walk_sit_wave",
          status: "ok",
          metrics: {
            max_joint_limit_violation_deg: 0,
            max_foot_slide: 0,
            max_target_error: 0,
            penetration_frames: 0,
            max_penetration_depth: 0,
            curve_reduction_error: 0
          },
          warnings: []
        }
      }
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: /scenes/i }).click();
  await expect(page.getByText("Chair", { exact: true })).toBeVisible();
  await expect(page.getByText(/240 bytes/i)).toBeVisible();
  await expect(page.getByText(/walkable_regions/i)).toBeVisible();

  await page.getByRole("tab", { name: /motion/i }).click();
  await expect(
    page.getByLabel("Motion").getByRole("heading", { name: /^motion$/i })
  ).toBeVisible();
  await page.getByRole("button", { name: /compile demo/i }).click();
  await expect(page.getByText(/1 editable tracks/i)).toBeVisible();
  await expect(page.getByText(/max target error 0/i)).toBeVisible();
});

test("opens the manual rig editor and mirrors bone selection", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("tab", { name: /rig editor/i }).click();
  await expect(page.getByRole("heading", { name: /manual rig editor/i })).toBeVisible();

  const canvas = page.locator("canvas.rig-stage-canvas");
  await expect(canvas).toBeVisible();
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox?.width ?? 0).toBeGreaterThan(300);
  expect(canvasBox?.height ?? 0).toBeGreaterThan(300);

  await page.getByRole("button", { name: /forearm_r/i }).click();
  await expect(page.getByRole("button", { name: /forearm_r/i })).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await expect(page.getByText("World tip")).toBeVisible();
});

test("manual wave canvas matches the visual golden", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("tab", { name: /rig editor/i }).click();
  await page.getByLabel("Labels").click();
  await page.getByLabel("Axes").click();
  await page.getByLabel("Animate").click();
  const playhead = page.getByLabel("Playhead");
  await playhead.fill("0.6");
  await playhead.press("Enter");

  await expect(page.locator("canvas.rig-stage-canvas")).toHaveScreenshot(
    "manual-wave-canvas.png",
    {
      animations: "disabled",
      maxDiffPixelRatio: 0.04
    }
  );
});
