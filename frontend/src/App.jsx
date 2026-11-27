import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [apiStatus, setApiStatus] = useState("checking...");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((d) => setApiStatus(d.status))
      .catch(() => setApiStatus("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 640, margin: "40px auto", padding: "0 16px" }}>
      <h1>Distributed Image Pipeline</h1>
      <p>API status: <strong>{apiStatus}</strong></p>
      {/* Planned: upload view, batch progress view, results gallery */}
    </main>
  );
}
