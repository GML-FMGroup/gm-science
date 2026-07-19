import fs from "node:fs";
import path from "node:path";

export interface DataTreeSummary {
  files: number;
  bytes: number;
}

export interface DataMigrationResult extends DataTreeSummary {
  source: string;
  destination: string;
}

export function readPersistedDataLocation(filePath: string): string {
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, "utf-8")) as { dataLocation?: unknown };
    return typeof payload.dataLocation === "string" ? payload.dataLocation.trim() : "";
  } catch {
    return "";
  }
}

export function writePersistedDataLocation(filePath: string, dataLocation: string): void {
  const normalized = path.resolve(dataLocation);
  const temporary = `${filePath}.tmp-${process.pid}`;
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(temporary, `${JSON.stringify({ dataLocation: normalized }, null, 2)}\n`, {
    encoding: "utf-8",
    mode: 0o600,
  });
  fs.renameSync(temporary, filePath);
  fs.chmodSync(filePath, 0o600);
}

export function assertSafeDataMigration(source: string, destination: string): void {
  const sourcePath = path.resolve(source);
  const destinationPath = path.resolve(destination);
  if (sourcePath === destinationPath) {
    throw new Error("The selected folder is already the gm-science data location.");
  }
  const sourceToDestination = path.relative(sourcePath, destinationPath);
  const destinationToSource = path.relative(destinationPath, sourcePath);
  if (
    (!sourceToDestination.startsWith("..") && !path.isAbsolute(sourceToDestination))
    || (!destinationToSource.startsWith("..") && !path.isAbsolute(destinationToSource))
  ) {
    throw new Error("The new data location cannot contain, or be contained by, the current data location.");
  }
  if (!fs.existsSync(sourcePath) || !fs.statSync(sourcePath).isDirectory()) {
    throw new Error("The current gm-science data location is unavailable.");
  }
  if (fs.existsSync(destinationPath)) {
    if (!fs.statSync(destinationPath).isDirectory()) {
      throw new Error("The selected data location is not a folder.");
    }
    if (fs.readdirSync(destinationPath).length > 0) {
      throw new Error("Choose an empty folder for the new gm-science data location.");
    }
  }
}

export function summarizeDataTree(root: string): DataTreeSummary {
  const summary: DataTreeSummary = { files: 0, bytes: 0 };
  const pending = [path.resolve(root)];
  while (pending.length > 0) {
    const current = pending.pop()!;
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name);
      if (entry.isSymbolicLink()) {
        continue;
      }
      if (entry.isDirectory()) {
        pending.push(entryPath);
      } else if (entry.isFile()) {
        summary.files += 1;
        summary.bytes += fs.statSync(entryPath).size;
      }
    }
  }
  return summary;
}

export async function copyDataRootAtomically(
  source: string,
  destination: string,
): Promise<DataMigrationResult> {
  assertSafeDataMigration(source, destination);
  const sourcePath = fs.realpathSync(path.resolve(source));
  const destinationPath = path.resolve(destination);
  const parent = path.dirname(destinationPath);
  const staging = path.join(parent, `.${path.basename(destinationPath)}.gm-science-migrating-${process.pid}-${Date.now()}`);
  fs.mkdirSync(parent, { recursive: true });
  try {
    await fs.promises.cp(sourcePath, staging, {
      recursive: true,
      dereference: false,
      verbatimSymlinks: true,
      errorOnExist: true,
      force: false,
    });
    const sourceSummary = summarizeDataTree(sourcePath);
    const destinationSummary = summarizeDataTree(staging);
    if (
      sourceSummary.files !== destinationSummary.files
      || sourceSummary.bytes !== destinationSummary.bytes
    ) {
      throw new Error("The copied data did not pass the file-count and byte-size verification.");
    }
    if (fs.existsSync(destinationPath)) {
      fs.rmdirSync(destinationPath);
    }
    fs.renameSync(staging, destinationPath);
    return {
      source: sourcePath,
      destination: destinationPath,
      ...destinationSummary,
    };
  } catch (error) {
    fs.rmSync(staging, { recursive: true, force: true });
    throw error;
  }
}
