import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";

const [propsPath, compositionId, outDir, framesJson, scaleText] = process.argv.slice(2);
const frames = JSON.parse(framesJson);
const scale = Number(scaleText);
if (!Array.isArray(frames) || frames.length < 1 || frames.length > 6 ||
    frames.some((f) => !Number.isInteger(f) || f < 0) || !Number.isFinite(scale) || scale <= 0 || scale > 1) {
  throw new Error("Paramètres de sonde invalides.");
}
const inputProps = { ...JSON.parse(await readFile(propsPath, "utf8")), auditLayout: true };
const serveUrl = await bundle({ entryPoint: path.resolve("src/remotion/index.tsx"), onProgress: () => {} });
const browser = await openBrowser("chrome", { logLevel: "error" });
try {
  const composition = await selectComposition({ serveUrl, id: compositionId, inputProps, puppeteerInstance: browser, logLevel: "error" });
  for (const frame of frames) {
    let report = null;
    await renderStill({
      serveUrl, composition, inputProps, frame, scale, imageFormat: "png",
      output: path.join(outDir, `frame-${frame}.png`),
      puppeteerInstance: browser, logLevel: "error",
      onBrowserLog(log) {
        const prefix = "STUDIO_LAYOUT_PROBE ";
        if (!log.text.startsWith(prefix)) return;
        const observed = JSON.parse(log.text.slice(prefix.length));
        if (observed.frame === frame) report = observed;
      },
    });
    if (!report) throw new Error(`Aucune mesure DOM reçue pour la frame ${frame}.`);
    await writeFile(path.join(outDir, `frame-${frame}.json`), JSON.stringify(report));
  }
} finally {
  await browser.close({ silent: true });
}
