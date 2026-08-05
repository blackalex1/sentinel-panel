let cpuCircularChart = null;
let ramCircularChart = null;
let swapCircularChart = null;
let diskCircularChart = null;

export function updateChart(cpu, ram, swap, disk) {
    const cpuCanvas = document.getElementById("cpuCircularChart");
    const ramCanvas = document.getElementById("ramCircularChart");
    const swapCanvas = document.getElementById("swapCircularChart");
    const diskCanvas = document.getElementById("diskCircularChart");
    if (!cpuCanvas || !ramCanvas || !swapCanvas || !diskCanvas) return;
    
    if (!cpuCircularChart && window.Chart) {
        const ctx = cpuCanvas.getContext("2d");
        cpuCircularChart = new window.Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [cpu, 100 - cpu],
                    backgroundColor: [
                        '#8b5cf6', // Фиолетовый
                        'rgba(255, 255, 255, 0.04)'
                    ],
                    borderWidth: 0,
                    cutout: '82%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });
    }
    
    if (!ramCircularChart && window.Chart) {
        const ctx = ramCanvas.getContext("2d");
        ramCircularChart = new window.Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [ram, 100 - ram],
                    backgroundColor: [
                        '#06b6d4', // Циановый
                        'rgba(255, 255, 255, 0.04)'
                    ],
                    borderWidth: 0,
                    cutout: '82%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });
    }
    
    if (!swapCircularChart && window.Chart) {
        const ctx = swapCanvas.getContext("2d");
        swapCircularChart = new window.Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [swap, 100 - swap],
                    backgroundColor: [
                        '#f43f5e', // Розовый
                        'rgba(255, 255, 255, 0.04)'
                    ],
                    borderWidth: 0,
                    cutout: '82%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });
    }
    
    if (!diskCircularChart && window.Chart) {
        const ctx = diskCanvas.getContext("2d");
        diskCircularChart = new window.Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [disk, 100 - disk],
                    backgroundColor: [
                        '#10b981', // Зеленый
                        'rgba(255, 255, 255, 0.04)'
                    ],
                    borderWidth: 0,
                    cutout: '82%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });
    }
    
    const WARNING_COLOR = '#ff0055';
    
    if (cpuCircularChart) {
        cpuCircularChart.data.datasets[0].data = [cpu, 100 - cpu];
        cpuCircularChart.data.datasets[0].backgroundColor[0] = (cpu >= 90) ? WARNING_COLOR : '#8b5cf6';
        cpuCircularChart.update();
    }
    if (ramCircularChart) {
        ramCircularChart.data.datasets[0].data = [ram, 100 - ram];
        ramCircularChart.data.datasets[0].backgroundColor[0] = (ram >= 90) ? WARNING_COLOR : '#06b6d4';
        ramCircularChart.update();
    }
    if (swapCircularChart) {
        swapCircularChart.data.datasets[0].data = [swap, 100 - swap];
        swapCircularChart.data.datasets[0].backgroundColor[0] = (swap >= 90) ? WARNING_COLOR : '#f43f5e';
        swapCircularChart.update();
    }
    if (diskCircularChart) {
        diskCircularChart.data.datasets[0].data = [disk, 100 - disk];
        diskCircularChart.data.datasets[0].backgroundColor[0] = (disk >= 90) ? WARNING_COLOR : '#10b981';
        diskCircularChart.update();
    }
    
    const cpuText = document.getElementById("cpu-chart-text");
    if (cpuText) {
        cpuText.innerText = `${cpu.toFixed(1)}%`;
        cpuText.style.color = (cpu >= 90) ? WARNING_COLOR : 'var(--text-primary)';
    }
    
    const ramText = document.getElementById("ram-chart-text");
    if (ramText) {
        ramText.innerText = `${ram.toFixed(1)}%`;
        ramText.style.color = (ram >= 90) ? WARNING_COLOR : 'var(--text-primary)';
    }
    
    const swapText = document.getElementById("swap-chart-text");
    if (swapText) {
        swapText.innerText = `${swap.toFixed(1)}%`;
        swapText.style.color = (swap >= 90) ? WARNING_COLOR : 'var(--text-primary)';
    }
    
    const diskText = document.getElementById("disk-chart-text");
    if (diskText) {
        diskText.innerText = `${disk.toFixed(1)}%`;
        diskText.style.color = (disk >= 90) ? WARNING_COLOR : 'var(--text-primary)';
    }
}
