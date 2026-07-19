import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./i18n";
// styles.css entra via theme.css dentro de @layer legacy (cascade: legacy < theme < utilities)
import "./styles/theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
