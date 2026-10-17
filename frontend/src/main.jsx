import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/noto-sans/latin-400.css";
import "@fontsource/noto-sans/latin-600.css";
import "@fontsource/noto-sans/latin-700.css";
import "@fontsource/noto-sans-gurmukhi/gurmukhi-400.css";
import "@fontsource/noto-sans-gurmukhi/gurmukhi-600.css";
import "@fontsource/noto-sans-gurmukhi/gurmukhi-700.css";
import "@fontsource/noto-sans-devanagari/devanagari-400.css";
import "@fontsource/noto-sans-devanagari/devanagari-600.css";
import "@fontsource/noto-sans-devanagari/devanagari-700.css";
import "./styles/app.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(<App />);
