import * as esbuild from "esbuild";

const isProd = process.env.NODE_ENV === "production";

await esbuild.build({
  entryPoints: ["src/ui/index.tsx"],
  bundle: true,
  outfile: "public/bundle.js",
  format: "iife",
  jsx: "automatic",
  jsxImportSource: "react",
  platform: "browser",
  target: ["es2022", "chrome100", "firefox100", "safari15"],
  define: {
    "process.env.NODE_ENV": JSON.stringify(isProd ? "production" : "development"),
  },
  minify: isProd,
  sourcemap: !isProd,
  logLevel: "info",
});
