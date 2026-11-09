import { defineConfig } from "@neon/config/v1";

// TrackAJob uses Neon for one thing: plain Postgres (ADR-0005).
// The bundled services (Auth, AI Gateway, Functions, Realtime) are removed
// because they are unused and the AI Gateway requires purchased credits.
// Branch policy: per-branch tuning
export default defineConfig({
  branch: (branch) => {
    if (branch.isDefault) {
      // Default branch: no overrides, uses project defaults
      return {};
    }
    if (!branch.exists) {
      // New non-default branches: auto-expire
      // Run `neon checkout <name>` to create a new branch with these settings
      return { ttl: "7d" };
    }
    // Existing branch: no changes
    return {};
  },
});
