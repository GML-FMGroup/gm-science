import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import electron from "vite-plugin-electron";
import renderer from "vite-plugin-electron-renderer";

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    ...(mode === "test"
      ? []
      : [
        electron([
          {
            entry: "electron/main/index.ts",
            vite: {
              build: {
                outDir: "dist-electron/main",
                emptyOutDir: false,
                rollupOptions: {
                  output: {
                    entryFileNames: "index.js",
                  },
                },
              },
            },
          },
        ]),
        renderer(),
      ]),
  ],
  resolve: {
    alias: {
      "@": new URL("./app/src", import.meta.url).pathname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
  },
}));
