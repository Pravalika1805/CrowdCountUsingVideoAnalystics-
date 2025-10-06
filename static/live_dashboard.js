let barCtx = document.getElementById("barChart").getContext("2d");
let lineCtx = document.getElementById("lineChart").getContext("2d");

let barChart = new Chart(barCtx, {
  type: "bar",
  data: { labels: [], datasets: [{ label: "Current Counts", data: [] }] }
});

let lineChart = new Chart(lineCtx, {
  type: "line",
  data: { labels: [], datasets: [] }
});

async function updateDashboard() {
  let res = await fetch("/zone_counts");
  let data = await res.json();

  let zoneList = document.getElementById("zoneCounts");
  let alertBox = document.getElementById("alerts");
  zoneList.innerHTML = "";
  alertBox.innerHTML = "";

  let labels = [], counts = [];

  data.forEach((z,i) => {
    let li = document.createElement("li");
    li.textContent = `${z.label}: ${z.count}`;
    zoneList.appendChild(li);

    labels.push(z.label);
    counts.push(z.count);

    if (z.count > z.threshold) {
      let warn = document.createElement("div");
      warn.classList.add("alert");
      warn.innerHTML = `⚠ Zone '${z.label}' exceeded threshold!`;
      alertBox.appendChild(warn);
    }
  });

  // Update bar chart
  barChart.data.labels = labels;
  barChart.data.datasets[0].data = counts;
  barChart.update();

  // Update line chart
  if (lineChart.data.labels.length > 20) {
    lineChart.data.labels.shift();
    lineChart.data.datasets.forEach(ds => ds.data.shift());
  }
  lineChart.data.labels.push(new Date().toLocaleTimeString());

  if (lineChart.data.datasets.length === 0) {
    data.forEach(z => {
      lineChart.data.datasets.push({
        label: z.label,
        data: [z.count],
        borderColor: "#" + Math.floor(Math.random()*16777215).toString(16),
        fill: false
      });
    });
  } else {
    data.forEach((z,i) => lineChart.data.datasets[i].data.push(z.count));
  }
  lineChart.update();
}

setInterval(updateDashboard, 2000);
