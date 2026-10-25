import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
) as { version: string };

/**
 * El commit que se esta compilando.
 *
 * En el deploy, Coolify puede pasar SOURCE_COMMIT como build arg (Advanced > Build >
 * Source commit availability). En un build local sale de git. Si no esta ninguno de los
 * dos, queda vacio y la app muestra la fecha del build en su lugar.
 */
function buildSha(): string {
  const fromEnv = (
    process.env.SOURCE_COMMIT ||
    process.env.VITE_BUILD_SHA ||
    ""
  ).trim();
  if (fromEnv) return fromEnv;
  try {
    return execSync("git rev-parse --short=7 HEAD", {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "";
  }
}

export default defineConfig({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_SHA__: JSON.stringify(buildSha()),
    // Momento del build: cambia en cada deploy, asi que sirve de respaldo cuando no
    // hay commit (build sin SOURCE_COMMIT y sin git).
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
