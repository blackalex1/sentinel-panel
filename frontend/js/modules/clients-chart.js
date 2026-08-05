import { apiFetch } from "../api.js";
import { showToast } from "../ui.js";
import { t } from "../i18n.js";

let trafficChartInstance = null;

export async function showClientTrafficChart(email) {
    const container = document.getElementById("client-traffic-chart-container");
    if (!container) return;
    
    // Fetch traffic data from the API
    const res = await apiFetch(`/api/clients/${email}/traffic`);
    if (!res || !res.success) {
        showToast(t("traffic_chart_load_error", "Не удалось загрузить данные трафика"), "error");
        return;
    }
    
    container.style.display = "block";
    
    const records = res.obj || [];
    const labels = records.map(r => r.date);
    // Convert bytes to GB for better reading in the chart
    const uploadData = records.map(r => r.up / (1024 * 1024 * 1024));
    const downloadData = records.map(r => r.down / (1024 * 1024 * 1024));
    
    const ctx = document.getElementById("client-traffic-canvas").getContext("2d");
    
    if (trafficChartInstance) {
        trafficChartInstance.destroy();
    }
    
    trafficChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: `${t("traffic_upload", "Загрузка")} (GB)`,
                    data: uploadData,
                    borderColor: '#2ed573',
                    backgroundColor: 'rgba(46, 213, 115, 0.1)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: `${t("traffic_download", "Скачивание")} (GB)`,
                    data: downloadData,
                    borderColor: '#ff4757',
                    backgroundColor: 'rgba(255, 71, 87, 0.1)',
                    tension: 0.3,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)'
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)'
                    }
                }
            }
        }
    });
}

// Register close button for the traffic chart
document.addEventListener("DOMContentLoaded", () => {
    const btnCloseChart = document.getElementById("btn-close-traffic-chart");
    if (btnCloseChart) {
        btnCloseChart.addEventListener("click", () => {
            const container = document.getElementById("client-traffic-chart-container");
            if (container) container.style.display = "none";
        });
    }
});

// Bind to window scope for compatibility
window.showClientTrafficChart = showClientTrafficChart;
