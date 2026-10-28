// Chart Management Module
class ChartManager {
    constructor() {
        this.monthlyChart = null;
        this.dailyChart = null;
        this.setupChartDefaults();
    }

    // Setup Chart.js default animations
    setupChartDefaults() {
        Chart.defaults.datasets.bar.animation = {
            duration: 1200,
            easing: 'easeInOutQuart',
            delay: (ctx) => ctx.dataIndex * 80
        };

        Chart.defaults.datasets.line.animation = {
            duration: 1200,
            easing: 'easeInOutQuart',
            delay: (ctx) => ctx.dataIndex * 30
        };
    }    // Tạo biểu đồ tháng (bao gồm kỳ hiện tại)
    createMonthlyChart(monthlyData, currentPeriod, onClickCallback) {
        if (this.monthlyChart) {
            this.monthlyChart.destroy();
        }

        // Chuẩn bị dữ liệu biểu đồ
        const labels = [];
        const consumptionData = [];
        const costData = [];
        const backgroundColors = [];
        const borderColors = [];

        const yearSet = new Set(monthlyData.SanLuong.map(item => item.Năm).filter(Boolean));
        const hasMultipleYears = yearSet.size > 1;
        const currentPeriodKey = currentPeriod ? `${currentPeriod.year}-${currentPeriod.month}` : null;
        const currentPeriodIndexes = new Set();

        // Check mobile view
        const isMobile = window.innerWidth < 768;

        // Thêm dữ liệu từ monthlyData
        monthlyData.SanLuong.forEach((item, index) => {
            // Loại bỏ chữ "Tháng " và rút gọn năm trên mobile
            let yearDisplay = item.Năm;
            if (isMobile && yearDisplay) {
                yearDisplay = yearDisplay.toString().slice(-2);
            }

            const monthLabel = hasMultipleYears && item.Năm
                ? `${item.Tháng}-${yearDisplay}`
                : `${item.Tháng}`;
            labels.push(monthLabel);

            // Dùng parseFloat thay vì parseInt để giữ số thập phân (kWh)
            const consumption = typeof item["Điện tiêu thụ (KWh)"] === 'number'
                ? item["Điện tiêu thụ (KWh)"]
                : parseFloat(item["Điện tiêu thụ (KWh)"] || 0);
            consumptionData.push(consumption);

            // Tìm dữ liệu tiền điện tương ứng
            const correspondingCost = monthlyData.TienDien.find(cost =>
                cost.Tháng === item.Tháng && (!item.Năm || cost.Năm === item.Năm)
            );
            const cost = correspondingCost
                ? (typeof correspondingCost["Tiền Điện"] === 'number' ? correspondingCost["Tiền Điện"] : parseInt(correspondingCost["Tiền Điện"]))
                : 0;
            costData.push(cost);

            const itemYear = typeof item.Năm === 'number' ? item.Năm : parseInt(item.Năm, 10);
            const itemMonth = typeof item.Tháng === 'number' ? item.Tháng : parseInt(item.Tháng, 10);

            const isCurrentPeriod = currentPeriodKey &&
                itemYear === currentPeriod.year &&
                itemMonth === currentPeriod.month;
            if (isCurrentPeriod) {
                currentPeriodIndexes.add(index);
            }

            backgroundColors.push(isCurrentPeriod ? 'rgba(255, 193, 7, 0.8)' : 'rgba(147, 112, 219, 0.8)');
            borderColors.push(isCurrentPeriod ? 'rgba(255, 193, 7, 1)' : 'rgba(147, 112, 219, 1)');
        });

        // Highlight tháng tiêu thụ cao nhất / thấp nhất
        if (consumptionData.length > 0) {
            const maxVal = Math.max(...consumptionData);
            const minVal = Math.min(...consumptionData);

            consumptionData.forEach((value, index) => {
                if (value === maxVal) {
                    backgroundColors[index] = 'rgba(46, 204, 64, 0.85)';
                    borderColors[index] = 'rgba(46, 204, 64, 1)';
                } else if (value === minVal) {
                    backgroundColors[index] = 'rgba(231, 76, 60, 0.85)';
                    borderColors[index] = 'rgba(231, 76, 60, 1)';
                }
            });
        }

        const ctx = document.getElementById('monthlyChart');
        this.monthlyChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Tiêu thụ (kWh)',
                        data: consumptionData,
                        backgroundColor: backgroundColors,
                        borderColor: borderColors,
                        borderWidth: 1,
                        yAxisID: 'y1',
                        datalabels: { display: false }
                    },
                    {
                        label: 'Hóa đơn (VND)',
                        data: costData,
                        backgroundColor: costData.map((_, index) =>
                            currentPeriodIndexes.has(index)
                                ? 'rgba(255, 152, 0, 0.8)'
                                : 'rgba(233, 97, 171, 0.8)'
                        ),
                        borderColor: costData.map((_, index) =>
                            currentPeriodIndexes.has(index)
                                ? 'rgba(255, 152, 0, 1)'
                                : 'rgba(233, 97, 171, 1)'
                        ),
                        borderWidth: 1,
                        yAxisID: 'y2',
                        datalabels: { display: false }
                    }
                ]
            }, options: {
                animation: {
                    duration: 800, // Giảm thời gian animation
                    easing: 'easeOutQuart'
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                hover: {
                    animationDuration: 0 // Tắt animation khi hover
                },
                scales: {
                    x: {
                        ticks: {
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor,
                            maxRotation: 0,
                            minRotation: 0,
                            autoSkip: false, // Hiển thị tất cả tháng nếu đủ chỗ
                            font: {
                                size: isMobile ? 10 : 12 // Giảm font size trên mobile
                            }
                        },
                        grid: {
                            color: this.getCurrentThemeColors().gridColor
                        }
                    }, y1: {
                        type: 'linear',
                        position: 'left',
                        beginAtZero: true,
                        ticks: {
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        },
                        title: {
                            display: true,
                            text: 'Tiêu thụ (kWh)',
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        }
                    }, y2: {
                        type: 'linear',
                        position: 'right',
                        beginAtZero: true,
                        ticks: {
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        },
                        title: {
                            display: true,
                            text: 'Hóa đơn (VND)',
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        },
                        grid: { drawOnChartArea: false }
                    }
                }, plugins: {
                    legend: {
                        labels: {
                            color: this.getCurrentThemeColors().textColor
                        }
                    },
                    tooltip: {
                        animation: {
                            duration: 0 // Tắt animation tooltip để tránh nháy
                        }, callbacks: {
                            label: function (context) {
                                // Regex mới linh hoạt: khớp "M", "M-YYYY" hoặc "M-YY"
                                const monthMatch = context.label.match(/^(\d{1,2})(?:-(\d{2,4}))?$/);
                                const labelMonth = monthMatch ? parseInt(monthMatch[1], 10) : null;
                                let labelYear = monthMatch && monthMatch[2] ? parseInt(monthMatch[2], 10) : null;

                                // Nếu year chỉ có 2 chữ số (mobile), chuyển về 4 chữ số để so sánh
                                if (labelYear !== null && labelYear < 100) {
                                    labelYear += 2000;
                                }

                                const isCurrentPeriod = currentPeriod &&
                                    labelMonth === currentPeriod.month &&
                                    (labelYear === null || labelYear === currentPeriod.year);

                                if (context.datasetIndex === 0) {
                                    // Dataset tiêu thụ
                                    let label = `${context.dataset.label}: ${context.parsed.y.toFixed(2)} kWh`;
                                    if (isCurrentPeriod && currentPeriod) {
                                        label += `\n📅 Kỳ: ${currentPeriod.period.start.toLocaleDateString('vi-VN')} → ${currentPeriod.period.end.toLocaleDateString('vi-VN')}`;
                                        label += `\n📊 Đã có ${currentPeriod.days} ngày dữ liệu`;
                                    }
                                    return label;
                                } else {
                                    // Dataset hóa đơn
                                    let label = `${context.dataset.label}: ${context.parsed.y.toLocaleString()} VND`;
                                    if (isCurrentPeriod) {
                                        label += ` (tạm tính)`;
                                        if (currentPeriod && currentPeriod.details) {
                                            label += `\n💡 Trước thuế: ${currentPeriod.details.subtotal.toLocaleString()} VND`;
                                            label += `\n🏛️ Thuế 8%: ${currentPeriod.details.tax.toLocaleString()} VND`;
                                        }
                                    }
                                    return label;
                                }
                            }
                        }
                    }
                },
                maintainAspectRatio: false,
                responsive: true,
                onClick: onClickCallback
            }
        });

        return this.monthlyChart;
    }

    // Tạo biểu đồ ngày
    createDailyChart(filteredData) {
        const data = filteredData.filter(day => day["Điện tiêu thụ (kWh)"] > 0);
        data.sort((a, b) =>
            new Date(a.Ngày.split('-').reverse().join('-')) -
            new Date(b.Ngày.split('-').reverse().join('-'))
        );

        // Tính trend cho mỗi ngày
        data.forEach((day, idx, arr) => {
            if (idx === 0) {
                day._trend = 'flat';
                day._trendValue = 0;
            } else {
                const prev = arr[idx - 1]["Điện tiêu thụ (kWh)"];
                const val = day["Điện tiêu thụ (kWh)"];
                day._trend = val > prev ? 'up' : (val < prev ? 'down' : 'flat');
                day._trendValue = val - prev;
            }
        });

        const dailyLabels = data.map(day => day.Ngày);
        const dailyDataValues = data.map(day => day["Điện tiêu thụ (kWh)"]);

        // Highlight max/min
        const maxVal = Math.max(...dailyDataValues);
        const minVal = Math.min(...dailyDataValues);

        const pointBackgroundColors = dailyDataValues.map(v =>
            v === maxVal ? '#2ecc40' : v === minVal ? '#e74c3c' : 'rgba(233,97,171,0.6)'
        );
        const pointRadius = dailyDataValues.map(v =>
            v === maxVal || v === minVal ? 7 : 4
        );
        const pointStyle = dailyDataValues.map(v =>
            v === maxVal ? 'star' : v === minVal ? 'triangle' : 'circle'
        );

        if (this.dailyChart) {
            this.dailyChart.destroy();
        }

        const ctx = document.getElementById('dailyChart');
        this.dailyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dailyLabels,
                datasets: [{
                    label: 'Tiêu thụ (kWh)',
                    data: dailyDataValues,
                    fill: true,
                    backgroundColor: 'rgba(233, 97, 171, 0.2)',
                    borderColor: data.map((day, idx) => {
                        if (idx === 0) return 'rgba(147, 112, 219, 1)';
                        if (day._trend === 'up') return 'rgba(46, 204, 113, 1)';
                        if (day._trend === 'down') return 'rgba(231, 76, 60, 1)';
                        return 'rgba(147, 112, 219, 1)';
                    }),
                    segment: {
                        borderColor: ctx => {
                            const v = dailyDataValues[ctx.p0DataIndex];
                            if (v === maxVal) return '#2ecc40';
                            if (v === minVal) return '#e74c3c';
                            return data[ctx.p0DataIndex]._trend === 'up' ?
                                'rgba(46,204,113,1)' :
                                data[ctx.p0DataIndex]._trend === 'down' ?
                                    'rgba(231,76,60,1)' : 'rgba(147,112,219,1)';
                        }
                    }, tension: 0.4,
                    pointBackgroundColor: pointBackgroundColors,
                    pointRadius: pointRadius,
                    pointStyle: pointStyle,
                    pointHoverRadius: 8, // Giảm kích thước hover
                    pointHoverBackgroundColor: '#e961ab',
                    pointBorderWidth: 1, // Giảm border width
                }]
            }, options: {
                animation: {
                    duration: 800, // Giảm thời gian animation
                    easing: 'easeOutQuart'
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                hover: {
                    animationDuration: 0 // Tắt animation khi hover
                }, scales: {
                    x: {
                        ticks: {
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        },
                        grid: {
                            color: this.getCurrentThemeColors().gridColor
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: this.getCurrentThemeColors().axisColor || this.getCurrentThemeColors().textColor
                        }
                    }
                }, plugins: {
                    legend: {
                        labels: {
                            usePointStyle: true,
                            pointStyle: 'line',
                            pointStyleWidth: 32,
                            boxWidth: 32,
                            boxHeight: 8,
                            color: this.getCurrentThemeColors().textColor
                        }
                    },
                    tooltip: {
                        animation: {
                            duration: 0 // Tắt animation tooltip để tránh nháy
                        },
                        callbacks: {
                            label: function (context) {
                                const idx = context.dataIndex;
                                const day = data[idx];
                                let label = `${context.dataset.label}: ${context.parsed.y.toFixed(2)} kWh`;

                                if (typeof day._trend !== 'undefined' && idx > 0) {
                                    const trendText = day._trend === 'up' ? '↗️' :
                                        day._trend === 'down' ? '↘️' : '➡️';
                                    label += ` ${trendText} ${day._trendValue > 0 ? '+' : ''}${day._trendValue.toFixed(2)}`;
                                }

                                if (context.parsed.y === maxVal) label += '  ⭐ Max';
                                if (context.parsed.y === minVal) label += '  🥇 Min';
                                label += `\nNgày: ${day.Ngày}`;
                                return label;
                            }
                        }
                    }
                },
                maintainAspectRatio: false,
                responsive: true
            }
        });

        return this.dailyChart;
    }

    // Highlight cột lớn nhất/nhỏ nhất bằng hiệu ứng glow
    highlightBarGlow(chart, color = '#e961ab') {
        if (!chart) return;

        const ctx = chart.ctx;
        const dataset = chart.data.datasets[0];
        if (!dataset) return;

        const max = Math.max(...dataset.data);
        const min = Math.min(...dataset.data);

        chart.getDatasetMeta(0).data.forEach((bar, i) => {
            if (dataset.data[i] === max || dataset.data[i] === min) {
                ctx.save();
                ctx.shadowColor = color;
                ctx.shadowBlur = 18;
                ctx.globalAlpha = 0.7;
                ctx.beginPath();
                ctx.arc(bar.x, bar.y, 18, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.restore();
            }
        });
    }

    // Update charts khi đổi theme
    updateChartsTheme() {
        const currentTheme = document.body.getAttribute('data-theme') || 'dark-gradient';
        const themeConfig = this.getThemeChartConfig(currentTheme);

        const applyToScale = (scales, id) => {
            if (scales && scales[id]) {
                if (scales[id].ticks) scales[id].ticks.color = themeConfig.axisColor || themeConfig.textColor;
                if (scales[id].grid) scales[id].grid.color = themeConfig.gridColor;
                if (scales[id].title) scales[id].title.color = themeConfig.axisColor || themeConfig.textColor;
            }
        };

        // Monthly chart: axes are x, y1, y2
        if (this.monthlyChart) {
            this.monthlyChart.options.plugins.legend.labels.color = themeConfig.textColor;
            const s = this.monthlyChart.options.scales;
            applyToScale(s, 'x');
            applyToScale(s, 'y1');
            applyToScale(s, 'y2');
            this.monthlyChart.update('none');
        }

        // Daily chart: axes are x, y
        if (this.dailyChart) {
            this.dailyChart.options.plugins.legend.labels.color = themeConfig.textColor;
            const s = this.dailyChart.options.scales;
            applyToScale(s, 'x');
            applyToScale(s, 'y');
            this.dailyChart.update('none');
        }
    }

    // Get theme-specific chart configuration
    getThemeChartConfig(themeName) {
        const configs = {
            'dark-gradient': { textColor: '#e0e0e0', axisColor: '#f5f5f5', gridColor: 'rgba(224, 224, 224, 0.1)' },
            'cyberpunk': { textColor: '#00ff9f', axisColor: '#f5f5f5', gridColor: 'rgba(0, 255, 159, 0.2)' },
            'neon-dreams': { textColor: '#ffffff', axisColor: '#ffffff', gridColor: 'rgba(255, 20, 147, 0.2)' },
            'aurora-borealis': { textColor: '#ffffff', axisColor: '#ffffff', gridColor: 'rgba(26, 140, 255, 0.2)' },
            'synthwave': { textColor: '#ff00ff', axisColor: '#ffffff', gridColor: 'rgba(255, 0, 255, 0.2)' },
            'glassmorphism': { textColor: '#333333', axisColor: '#555555', gridColor: 'rgba(51, 51, 51, 0.1)' },
            'neubrutalism': { textColor: '#000000', axisColor: '#333333', gridColor: 'rgba(0, 0, 0, 0.3)' },
            'matrix-rain': { textColor: '#00ff00', axisColor: '#f5f5f5', gridColor: 'rgba(0, 255, 0, 0.2)' },
            'sunset-vibes': { textColor: '#ffffff', axisColor: '#ffffff', gridColor: 'rgba(255, 255, 255, 0.2)' },
            'ocean-depth': { textColor: '#87ceeb', axisColor: '#f5f5f5', gridColor: 'rgba(135, 206, 235, 0.2)' },
            'midnight-purple': { textColor: '#dda0dd', axisColor: '#f5f5f5', gridColor: 'rgba(221, 160, 221, 0.2)' },
            'golden-hour': { textColor: '#8b4513', axisColor: '#f5f5f5', gridColor: 'rgba(139, 69, 19, 0.2)' },
            'forest-mist': { textColor: '#f0fff0', axisColor: '#ffffff', gridColor: 'rgba(240, 255, 240, 0.2)' },
            'cosmic-dust': { textColor: '#e6e6fa', axisColor: '#ffffff', gridColor: 'rgba(230, 230, 250, 0.2)' },
            'tokyo-night': { textColor: '#a9b1d6', axisColor: '#f5f5f5', gridColor: 'rgba(169, 177, 214, 0.2)' },
            'minimal-light': { textColor: '#333333', axisColor: '#555555', gridColor: 'rgba(51, 51, 51, 0.1)' }
        };

        return configs[themeName] || configs['dark-gradient'];
    }

    // Get current theme colors
    getCurrentThemeColors() {
        const currentTheme = document.body.getAttribute('data-theme') || 'dark-gradient';
        return this.getThemeChartConfig(currentTheme);
    }

    // Destroy both charts
    destroyCharts() {
        if (this.monthlyChart) {
            this.monthlyChart.destroy();
            this.monthlyChart = null;
        }
        if (this.dailyChart) {
            this.dailyChart.destroy();
            this.dailyChart = null;
        }
    }
}

// Export cho sử dụng global
window.ChartManager = ChartManager;
