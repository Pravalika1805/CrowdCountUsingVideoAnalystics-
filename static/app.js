const streamImg = document.getElementById("stream");
const canvas = document.getElementById("drawCanvas");

if (streamImg && canvas) {
  // Resize canvas to match video
  function resizeCanvas() {
    canvas.width = streamImg.clientWidth;
    canvas.height = streamImg.clientHeight;
  }
  resizeCanvas();
  new ResizeObserver(resizeCanvas).observe(streamImg);
}

let ctx = canvas ? canvas.getContext("2d") : null;
let drawing = false, startX, startY, endX, endY;
let tempZone = null;

// --- Draw Zone ---
document.getElementById("btnDraw")?.addEventListener("click", () => {
  if (!canvas) return;
  canvas.onmousedown = e => {
    const r = canvas.getBoundingClientRect();
    startX = e.clientX - r.left;
    startY = e.clientY - r.top;
    drawing = true;
  };
  canvas.onmouseup = e => {
    if (!drawing) return;
    const r = canvas.getBoundingClientRect();
    endX = e.clientX - r.left;
    endY = e.clientY - r.top;
    drawing = false;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "red";
    ctx.lineWidth = 2;
    ctx.strokeRect(startX, startY, endX - startX, endY - startY);

    tempZone = { coordinates: [[Math.round(startX), Math.round(startY)], [Math.round(endX), Math.round(endY)]] };
    alert("Zone drawn! Now click 'Name Zone'.");
  };
});

// --- Name Zone ---
document.getElementById("btnName")?.addEventListener("click", () => {
  if (!tempZone) return alert("Draw a zone first!");
  const label = prompt("Enter Zone Name:", "Zone");
  if (!label) return;
  const th = prompt("Enter Threshold:", "5");
  if (!th || isNaN(th)) return;
  tempZone.label = label.trim();
  tempZone.threshold = parseInt(th);
  alert(`Zone named "${tempZone.label}". Now click 'Save Zone'.`);
});

// --- Save Zone ---
document.getElementById("btnSave")?.addEventListener("click", async () => {
  if (!tempZone || !tempZone.label) {
    alert("Please draw and name the zone first!");
    return;
  }
  const res = await fetch("/zones", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tempZone)
  });
  const out = await res.json();
  if (out.status === "saved") {
    alert(`Zone '${tempZone.label}' saved!`);
    tempZone = null;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  } else {
    alert("Error saving zone.");
  }
});

// --- Delete Last Zone ---
document.getElementById("btnDeleteLast")?.addEventListener("click", async () => {
  const res = await fetch("/zones", { method: "DELETE" });
  const out = await res.json();
  alert(out.status === "deleted" ? "Last zone deleted." : "No zones to delete.");
});

// --- Update Live Counts ---
async function updateCounts() {
  const countsDiv = document.getElementById("zoneCounts");
  const alertsDiv = document.getElementById("alertsPanel");
  if (!countsDiv) return; // <-- only after video upload

  const res = await fetch("/zone_counts");
  const data = await res.json();

  let html = `<div>Total: ${data.total}</div>`;
  for (const [zone, c] of Object.entries(data.zones)) {
    html += `<div>${zone}: <strong>${c}</strong></div>`;
  }
  countsDiv.innerHTML = html;

  if (data.alerts.length) {
    alertsDiv.innerHTML = data.alerts.map(a => `<div class="alert alert-danger py-1">${a}</div>`).join("");
  } else {
    alertsDiv.innerHTML = `<span class="text-muted">No alerts</span>`;
  }
}

if (streamImg) {
  // ✅ Only start polling counts if video is uploaded
  setInterval(updateCounts, 3000);
}

















