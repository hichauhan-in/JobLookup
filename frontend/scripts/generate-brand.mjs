import { writeFile } from "node:fs/promises";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScanSearch } from "lucide-react";

const icon = renderToStaticMarkup(
  createElement(ScanSearch, { color: "#267b52", size: 64, strokeWidth: 1.7 }),
);
await writeFile(new URL("../public/favicon.svg", import.meta.url), icon);
