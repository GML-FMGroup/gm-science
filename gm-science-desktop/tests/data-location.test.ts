// @vitest-environment node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  assertSafeDataMigration,
  copyDataRootAtomically,
  readPersistedDataLocation,
  summarizeDataTree,
  writePersistedDataLocation,
} from "../electron/main/data-location";

const temporaryRoots: string[] = [];

function temporaryRoot(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gm-science-data-location-"));
  temporaryRoots.push(root);
  return root;
}

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

describe("gm-science data location migration", () => {
  it("persists a private absolute location atomically", () => {
    const root = temporaryRoot();
    const settingsPath = path.join(root, "settings", "data-location.json");
    writePersistedDataLocation(settingsPath, path.join(root, "data", "..", "science"));

    expect(readPersistedDataLocation(settingsPath)).toBe(path.join(root, "science"));
    expect(fs.statSync(settingsPath).mode & 0o777).toBe(0o600);
  });

  it("copies and verifies a complete data root before replacing an empty destination", async () => {
    const root = temporaryRoot();
    const source = path.join(root, "old");
    const destination = path.join(root, "new");
    fs.mkdirSync(path.join(source, "projects", "one"), { recursive: true });
    fs.writeFileSync(path.join(source, "projects", "one", "notes.md"), "evidence");
    fs.writeFileSync(path.join(source, "science.db"), "database");
    fs.mkdirSync(destination);

    const result = await copyDataRootAtomically(source, destination);

    expect(result).toMatchObject({ destination, files: 2, bytes: 16 });
    expect(fs.readFileSync(path.join(destination, "projects", "one", "notes.md"), "utf-8")).toBe("evidence");
    expect(fs.existsSync(path.join(source, "science.db"))).toBe(true);
    expect(summarizeDataTree(destination)).toEqual(summarizeDataTree(source));
  });

  it("rejects overlapping and non-empty destination folders", () => {
    const root = temporaryRoot();
    const source = path.join(root, "source");
    const destination = path.join(root, "destination");
    fs.mkdirSync(path.join(source, "nested"), { recursive: true });
    fs.mkdirSync(destination);
    fs.writeFileSync(path.join(destination, "existing.txt"), "keep");

    expect(() => assertSafeDataMigration(source, path.join(source, "nested"))).toThrow(/cannot contain/);
    expect(() => assertSafeDataMigration(source, root)).toThrow(/cannot contain/);
    expect(() => assertSafeDataMigration(source, destination)).toThrow(/empty folder/);
  });
});
