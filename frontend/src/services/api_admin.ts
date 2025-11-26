
export async function checkHealth(): Promise<any> {
  const res = await fetch("/api/admin/health");
  if (!res.ok) throw new Error("health check failed");
  return res.json();
}

export async function resetWorld(keepSaves: boolean, keepMap: boolean): Promise<any> {
  const res = await fetch("/api/admin/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keep_saves: keepSaves, keep_map: keepMap }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "reset world failed");
  }
  return res.json();
}

