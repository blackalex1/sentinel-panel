import { apiFetch } from "../../api.js";
import { t } from "../../i18n.js";
import { formatBytes } from "../../ui.js";
import { openGlobalTrafficDetailsModal } from "./traffic_modal.js";

let globalTrafficChartInstance = null;

export async function loadGlobalTrafficChart() {
    const canvas = document.getElementById("globalTrafficChart");
    if (!canvas) return;
    
    const res = await apiFetch("/panel/api/system/global-traffic");
    if (!res || !res.success) return;
    
    const records = res.obj || [];
    const labels = records.map(r => r.date);
    
    // Determine dynamic unit scaling (B, KB, MB, GB, TB)
    const maxBytes = Math.max(...records.map(r => Math.max(r.up || 0, r.down || 0)), 1);
    
    let unitScale = 1024 * 1024 * 1024; // Default GB
    let unitName = "GB";
    if (maxBytes < 1024 * 1024) {
        unitScale = 1024;
        unitName = "KB";
    } else if (maxBytes < 1024 * 1024 * 1024) {
        unitScale = 1024 * 1024;
        unitName = "MB";
    } else if (maxBytes < 1024 * 1024 * 1024 * 1024) {
        unitScale = 1024 * 1024 * 1024;
        unitName = "GB";
    } else {
        unitScale = 1024 * 1024 * 1024 * 1024;
        unitName = "TB";
    }

    const uploadData = records.map(r => parseFloat(((r.up || 0) / unitScale).toFixed(2)));
    const downloadData = records.map(r => parseFloat(((r.down || 0) / unitScale).toFixed(2)));
    
    const ctx = canvas.getContext("2d");
    
    if (globalTrafficChartInstance) {
        globalTrafficChartInstance.destroy();
    }
    
    if (window.Chart) {
        globalTrafficChartInstance = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: `${t("traffic_upload", "Загрузка")} (${unitName})`,
                        data: uploadData,
                        borderColor: '#10b981',
                        backgroundColor: (context) => {
                            const chart = context.chart;
                            const {ctx, chartArea} = chart;
                            if (!chartArea) return 'rgba(16, 185, 129, 0.2)';
                            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                            gradient.addColorStop(0, 'rgba(16, 185, 129, 0.35)');
                            gradient.addColorStop(1, 'rgba(16, 185, 129, 0.02)');
                            return gradient;
                        },
                        borderWidth: 1.5,
                        borderRadius: 4,
                        barPercentage: 0.75,
                        categoryPercentage: 0.75
                    },
                    {
                        label: `${t("traffic_download", "Скачивание")} (${unitName})`,
                        data: downloadData,
                        borderColor: '#f43f5e',
                        backgroundColor: (context) => {
                            const chart = context.chart;
                            const {ctx, chartArea} = chart;
                            if (!chartArea) return 'rgba(244, 63, 94, 0.2)';
                            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                            gradient.addColorStop(0, 'rgba(244, 63, 94, 0.35)');
                            gradient.addColorStop(1, 'rgba(244, 63, 94, 0.02)');
                            return gradient;
                        },
                        borderWidth: 1.5,
                        borderRadius: 4,
                        barPercentage: 0.75,
                        categoryPercentage: 0.75
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: 'rgba(255, 255, 255, 0.7)',
                            font: { family: "'Outfit', 'Inter', 'Segoe UI', sans-serif", size: 12, weight: 600 }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        borderColor: 'rgba(255, 255, 255, 0.08)',
                        borderWidth: 1,
                        titleFont: { family: "'Outfit', 'Inter', 'Segoe UI', sans-serif", size: 12, weight: 600 },
                        bodyFont: { family: "'Outfit', 'Inter', 'Segoe UI', sans-serif", size: 12 },
                        padding: 12,
                        cornerRadius: 8,
                        displayColors: true,
                        callbacks: {
                            label: function(context) {
                                const isUpload = context.datasetIndex === 0;
                                const rec = records[context.dataIndex];
                                const rawBytes = isUpload ? (rec ? rec.up : 0) : (rec ? rec.down : 0);
                                const title = isUpload ? t("traffic_upload", "Загрузка") : t("traffic_download", "Скачивание");
                                return ` ${title}: ${formatBytes(rawBytes)}`;
                            }
                        }
                    }
                },
                onClick: (event, elements) => {
                    if (elements && elements.length > 0) {
                        const index = elements[0].index;
                        const clickedDate = labels[index];
                        if (clickedDate) {
                            openGlobalTrafficDetailsModal(clickedDate);
                        }
                    }
                },
                onHover: (event, elements) => {
                    if (event.native && event.native.target) {
                        event.native.target.style.cursor = (elements && elements.length > 0) ? 'pointer' : 'default';
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.5)',
                            font: { family: "'Outfit', 'Inter', 'Segoe UI', sans-serif", size: 10 }
                        }
                    },
                    y: {
                        min: 0,
                        suggestedMax: 1,
                        grid: { color: 'rgba(255, 255, 255, 0.03)' },
                        ticks: {
                            color: 'rgba(255, 255, 255, 0.5)',
                            font: { family: "'Outfit', 'Inter', 'Segoe UI', sans-serif", size: 10 },
                            callback: function(value) {
                                return value + ' ' + unitName;
                            }
                        }
                    }
                }
            }
        });
    }

    const btnDetails = document.getElementById("btn-open-traffic-details");
    if (btnDetails && !btnDetails._hasClick) {
        btnDetails._hasClick = true;
        btnDetails.addEventListener("click", () => {
            const todayStr = new Date().toISOString().split("T")[0];
            openGlobalTrafficDetailsModal(todayStr);
        });
    }
}
