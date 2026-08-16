export default function HomePage() {
  return (
    <main style={{ padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "2rem", marginBottom: "1rem" }}>
        Self-Correcting API Broker
      </h1>
      <p style={{ color: "#94a3b8", marginBottom: "2rem" }}>
        Reliability layer with contextual graph learning. Dashboard is being built.
      </p>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {[
          { href: "/dashboard", label: "Dashboard" },
          { href: "/apis", label: "API Registry" },
          { href: "/broker", label: "Broker Console" },
          { href: "/recovery-memory", label: "Recovery Memory" },
          { href: "/graph", label: "Graph Explorer" },
          { href: "/evaluation", label: "Evaluation" },
        ].map(({ href, label }) => (
          <a
            key={href}
            href={href}
            style={{
              padding: "0.75rem 1.5rem",
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              color: "#e2e8f0",
              textDecoration: "none",
              fontSize: "0.9rem",
            }}
          >
            {label}
          </a>
        ))}
      </div>
    </main>
  );
}
