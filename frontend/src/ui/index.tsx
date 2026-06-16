import React from "react";
import { createRoot } from "react-dom/client";
import Dashboard from "./dashboard.js";

const el = document.getElementById("root");
if (!el) throw new Error("Root element #root not found");

createRoot(el).render(
  <React.StrictMode>
    <Dashboard />
  </React.StrictMode>
);
