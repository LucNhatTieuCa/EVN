// Detect if running inside Home Assistant frontend (global, as early as possible)

// UI Management Module
class UIManager {
    constructor() {
        this.setupEventListeners();
        this.setupAnimations();
        this.updateCustomerHeader();
    }    // Load header title from localStorage
    updateCustomerHeader() {
        const select=document.getElementById('accountSelect');
        const option=select?.selectedOptions?.[0];
        const name=option?.dataset.customerName||option?.value||'EVN MONITOR';
        const header=document.getElementById('customerHeader');
        if(header)header.textContent=name;
    }
    setupEventListeners() {
        // Ripple effect for all buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('btn')) {
                this.createRippleEffect(e);
            }
        });

        // Theme selector
        const themeSelector = document.getElementById('themeSelect');
        if (themeSelector) {
            themeSelector.addEventListener('change', (e) => this.changeTheme(e.target.value));
            // Load saved theme
            this.loadSavedTheme();
        }
    }

    // Tạo ripple effect
    createRippleEffect(e) {
        const btn = e.target;
        const circle = document.createElement('span');
        circle.className = 'ripple';

        const rect = btn.getBoundingClientRect();
        circle.style.left = (e.clientX - rect.left) + 'px';
        circle.style.top = (e.clientY - rect.top) + 'px';
        circle.style.width = circle.style.height = Math.max(rect.width, rect.height) + 'px';

        btn.appendChild(circle);
        setTimeout(() => circle.remove(), 600);
    }    // Change theme function
    changeTheme(themeName) {
        // Remove all existing theme classes
        const themes = [
            'dark-gradient', 'cyberpunk', 'neon-dreams', 'aurora-borealis',
            'synthwave', 'glassmorphism', 'neubrutalism', 'matrix-rain',
            'sunset-vibes', 'ocean-depth', 'midnight-purple', 'golden-hour',
            'forest-mist', 'cosmic-dust', 'tokyo-night', 'minimal-light'
        ];
        themes.forEach(theme => {
            document.body.removeAttribute('data-theme');
        });
        // Apply new theme
        document.body.setAttribute('data-theme', themeName);
        // Save theme preference (safe)
        if (!window.__DISABLE_THEME_PERSISTENCE__ && this.isLocalStorageAvailable()) {
            try {
                localStorage.setItem('uiTheme', themeName);
            } catch (e) {
                console.warn('Could not save theme to localStorage:', e);
                window.__DISABLE_THEME_PERSISTENCE__ = true;
            }
        }
        // Update theme selector value
        const themeSelector = document.getElementById('themeSelect');
        if (themeSelector) {
            themeSelector.value = themeName;
        }
        // Apply theme to form elements
        this.applyThemeToFormElements(themeName);
        // Trigger chart updates
        if (window.chartManager) {
            window.chartManager.updateChartsTheme();
        }

    }
    // Apply theme to form elements and containers
    applyThemeToFormElements(themeName) {
        // Apply to form elements
        const formElements = document.querySelectorAll('select, input[type="date"]');
        formElements.forEach(element => {
            // Remove any existing theme classes
            element.className = element.className.replace(/theme-\w+/g, '');
            // Add new theme class if needed (handled by CSS data-theme attribute)
        });

        // Apply to search results container
        const searchResultsContainer = document.getElementById('searchResult');
        if (searchResultsContainer) {
            searchResultsContainer.style.transition = 'background-color 0.5s, border-color 0.5s, box-shadow 0.5s';
        }
    }

    // Load saved theme
    loadSavedTheme() {
        let savedTheme = 'dark-gradient';
        const validThemes = [
            'dark-gradient', 'cyberpunk', 'neon-dreams', 'aurora-borealis',
            'synthwave', 'glassmorphism', 'neubrutalism', 'matrix-rain',
            'sunset-vibes', 'ocean-depth', 'midnight-purple', 'golden-hour',
            'forest-mist', 'cosmic-dust', 'tokyo-night', 'minimal-light'
        ];
        if (!window.__DISABLE_THEME_PERSISTENCE__ && this.isLocalStorageAvailable()) {
            try {
                const theme = localStorage.getItem('uiTheme');
                if (theme && typeof theme === 'string' && validThemes.includes(theme)) {
                    savedTheme = theme;
                } else {
                    localStorage.removeItem('uiTheme');
                }
            } catch (e) {
                console.warn('Could not read theme from localStorage:', e);
                window.__DISABLE_THEME_PERSISTENCE__ = true;
            }
        }
        this.changeTheme(savedTheme);
        // Đảm bảo luôn lưu lại key uiTheme nếu chưa có (kể cả lần đầu vào trang)
        if (!window.__DISABLE_THEME_PERSISTENCE__ && this.isLocalStorageAvailable()) {
            try {
                localStorage.setItem('uiTheme', savedTheme);
            } catch (e) {
                // Không làm gì nếu localStorage không truy cập được
            }
        }
    }

    // Get theme display name
    getThemeDisplayName(themeName) {
        const themeNames = {
            'dark-gradient': 'Dark Gradient',
            'cyberpunk': 'Cyberpunk 2025',
            'neon-dreams': 'Neon Dreams',
            'aurora-borealis': 'Aurora Borealis',
            'synthwave': 'Synthwave',
            'glassmorphism': 'Glassmorphism',
            'neubrutalism': 'Neubrutalism',
            'matrix-rain': 'Matrix Rain',
            'sunset-vibes': 'Sunset Vibes',
            'ocean-depth': 'Ocean Depth',
            'midnight-purple': 'Midnight Purple',
            'golden-hour': 'Golden Hour',
            'forest-mist': 'Forest Mist',
            'cosmic-dust': 'Cosmic Dust',
            'tokyo-night': 'Tokyo Night',
            'minimal-light': 'Minimal Light'
        };
        return themeNames[themeName] || themeName;
    }

    // Populate year select dropdown
    populateYearSelect(years) {
        const yearSelect = document.getElementById('yearSelect');
        if (!yearSelect) return;

        // Keep the "all" option
        const currentValue = yearSelect.value;
        yearSelect.innerHTML = '<option value="all">Tất cả các năm</option>';

        // Add year options in descending order
        years.sort((a, b) => b - a).forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = year;
            yearSelect.appendChild(option);
        });

        // Restore selection if still valid
        if (currentValue && (currentValue === 'all' || years.includes(parseInt(currentValue)))) {
            yearSelect.value = currentValue;
        }
    }

    // Render summary container    // Render summary container - Old design style
    renderSummaryContainer(trendData) {
        const summaryContainer = document.getElementById('summaryContainer');
        summaryContainer.innerHTML = '';

        // Check if mobile for additional responsive class
        const isMobile = window.innerWidth <= 480;

        trendData.forEach((data, index) => {
            const summaryDiv = document.createElement('div');
            summaryDiv.className = 'summary-month-card';
            summaryDiv.id = `summary-month-${index}`;

            // Determine trend color and symbol
            let trendSymbol = '—';
            let trendClass = 'neutral';
            if (data.trend === 'up') {
                trendSymbol = '▲';
                trendClass = 'positive';
            } else if (data.trend === 'down') {
                trendSymbol = '▼';
                trendClass = 'negative';
            } summaryDiv.innerHTML = `
                <h4>${data.isCurrentPeriod ? 'Kỳ này' : `Tháng ${data.monthNum.toString().padStart(2, '0')}`}</h4>
                <div class="summary-stat-inline">
                    <i class="fas fa-bolt text-yellow-400"></i>
                    <span>Tổng:</span>
                    <strong>${data.totalConsumption.toFixed(1)}</strong>
                    <span>kWh</span>
                </div>
                <div class="summary-stat-inline">
                    <i class="fas fa-coins text-green-400"></i>
                    <span>Tiền:</span>
                    <strong>${Number.isFinite(data.monthlyCost) && (data.isCurrentPeriod || data.hasOfficialBill !== false) ? data.monthlyCost.toLocaleString() : "Chưa có dữ liệu"}</strong>
                    <span>VND</span>
                </div>                <div class="summary-stat-row">
                    <span class="min-value">
                        Min: <i class="fas fa-arrow-down text-blue-500"></i><strong class="text-blue-500">${data.min.toFixed(1)}</strong>
                    </span>
                    <span class="max-value">
                        Max: <i class="fas fa-arrow-up text-red-500"></i><strong class="text-red-500">${data.max.toFixed(1)}</strong>
                    </span>
                </div>
                <div class="summary-change ${trendClass}" style="display: flex; justify-content: space-between; align-items: center; font-size: min(0.85em, 3.2vw); margin-top: 4px;">
                    <span class="summary-trend" style="font-size: clamp(0.7em, 2vw, 1em);">
                        ${trendSymbol} ${data.trendValue > 0 ? '+' : ''}${data.trendValue.toFixed(2)} (${data.trendPercent > 0 ? '+' : ''}${data.trendPercent.toFixed(1)}%)
                    </span>
                    <span class="summary-avg" style="color: var(--text-secondary); font-size: clamp(0.7em, 2vw, 1em);">
                        Avg: <strong style="color: var(--text-primary);">${data.avg.toFixed(1)}</strong>
                    </span>
                </div>
            `;
            summaryContainer.appendChild(summaryDiv);
        });
    }

    // Update summary numbers with animation
    updateSummaryNumbers(summary) {
        this.animateCounterUp(document.getElementById('totalCost'), summary.totalCost, 0);
        this.animateCounterUp(document.getElementById('avgMonthlyCost'), summary.avgMonthlyCost, 0);
        this.animateCounterUp(document.getElementById('avgMonthlyConsumption'), summary.avgMonthlyConsumption, 2);
        this.animateCounterUp(document.getElementById('avgDailyConsumption'), summary.avgDailyConsumption, 2);
    }

    // Counter up animation
    animateCounterUp(element, value, decimals = 0) {
        if (!element) return;

        const duration = 900;
        const start = parseFloat(element.textContent.replace(/,/g, '')) || 0;
        const end = value;
        const startTime = performance.now();

        if (start === end) return;

        const animate = (now) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const current = start + (end - start) * progress;

            if (decimals > 0) {
                element.textContent = current.toLocaleString(undefined, { maximumFractionDigits: decimals });
            } else {
                element.textContent = Math.round(current).toLocaleString();
            }

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                element.textContent = decimals > 0 ?
                    end.toLocaleString(undefined, { maximumFractionDigits: decimals }) :
                    Math.round(end).toLocaleString();
                element.classList.add('changed');
                setTimeout(() => element.classList.remove('changed'), 700);
            }
        };

        requestAnimationFrame(animate);
    }

    // Populate month select
    populateMonthSelect(uniqueMonths) {
        const monthSelect = document.getElementById('monthSelect');
        monthSelect.innerHTML = '';

        uniqueMonths.forEach(monthYear => {
            const option = document.createElement('option');
            option.value = monthYear;
            option.textContent = `Tháng ${monthYear}`;
            monthSelect.appendChild(option);
        });

        if (uniqueMonths.length > 0) {
            monthSelect.value = uniqueMonths[0];
        }
    }

    // Populate account select
    populateAccountSelect(accounts) {
        const accountSelect = document.getElementById('accountSelect');
        accountSelect.innerHTML = '';

        accounts.forEach((account, index) => {
            const option = document.createElement('option');
            option.value = account.userevn;
            option.dataset.customerName=account.name||account.userevn;
            option.textContent=option.dataset.customerName===account.userevn?account.userevn:`${option.dataset.customerName} · ${account.userevn}`;
            accountSelect.appendChild(option);
            if (index === 0) option.selected = true;
        });
        this.updateCustomerHeader();
    }

    // Update account avatar
    updateAccountAvatar(account) {
        const avatar = document.getElementById('accountAvatar');
        if (!avatar) return;

        if (!account) {
            avatar.innerHTML = '<i class="fas fa-user"></i>';
            return;
        }

        // Lấy ký tự đầu hoặc số cuối tài khoản làm avatar
        let display = account[0];
        if (/\d/.test(account[account.length - 1])) {
            display = account[account.length - 1];
        }
        avatar.textContent = display;
    }    // Render search results - simplified as we now use the modal dialog directly
    renderSearchResults(filteredData, summary = null, showSummary = false) {
        // This function is kept for compatibility, but we now show results directly in the modal
        // The search results container is no longer used
    }// Khởi tạo ô kết quả tìm kiếm - not needed anymore as we now use the detail modal directly
    initializeSearchResults() {
        // This function is kept for compatibility but no longer needs to do anything
        // since we're now showing results directly in the modal popup
    }

    // Clear all data displays
    clearData() {
        const elements = ['totalCost', 'avgMonthlyCost', 'avgMonthlyConsumption', 'avgDailyConsumption'];
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) element.textContent = '';
        });

        const monthSelect = document.getElementById('monthSelect');
        if (monthSelect) monthSelect.innerHTML = '';

        const searchResult = document.getElementById('searchResult');
        if (searchResult) searchResult.innerHTML = '';

        const summaryContainer = document.getElementById('summaryContainer');
        if (summaryContainer) summaryContainer.innerHTML = '';
    }

    // Show/hide loader
    showLoader(show = true) {
        const loader = document.getElementById('mainLoader');
        if (loader) {
            loader.style.display = show ? 'block' : 'none';
        }
    }

    // Setup SVG background animation
    setupAnimations() {
        this.animateSVGBackground();
    }

    // Animate SVG Background
    animateSVGBackground() {
        const c1 = document.getElementById('bg-c1');
        const c2 = document.getElementById('bg-c2');
        const e1 = document.getElementById('bg-e1');

        if (!c1 || !c2 || !e1) return;

        let t = 0;
        const loop = () => {
            t += 0.008;
            c1.setAttribute('cx', 400 + Math.sin(t) * 60);
            c1.setAttribute('cy', 300 + Math.cos(t / 2) * 40);
            c2.setAttribute('cx', 1600 + Math.cos(t / 1.5) * 80);
            c2.setAttribute('cy', 800 + Math.sin(t / 1.2) * 60);
            e1.setAttribute('rx', 120 + Math.sin(t / 1.3) * 18);
            e1.setAttribute('ry', 60 + Math.cos(t / 1.7) * 10);
            requestAnimationFrame(loop);
        };
        loop();
    }

    // Hiển thị toast notification
    showToast(message, type = 'success') {
        // Remove existing toast if any
        const existingToast = document.querySelector('.toast-notification');
        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
                <span>${message}</span>
            </div>
        `;

        document.body.appendChild(toast);

        // Auto remove after 3 seconds
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    // Hiển thị dữ liệu 5 ngày gần đây trong card tìm kiếm
    displayRecentDays(recentData) {
        const recentDaysContainer = document.getElementById('recentDaysData');
        if (!recentDaysContainer) return;

        recentDaysContainer.innerHTML = '';

        if (!recentData || recentData.length === 0) {
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'text-sm text-gray-400 text-center py-2';
            emptyMessage.textContent = 'Không có dữ liệu gần đây';
            recentDaysContainer.appendChild(emptyMessage);
            return;
        }

        const values = recentData.map(day => Number(day["Điện tiêu thụ (kWh)"])).filter(Number.isFinite);
        const minimum = Math.min(...values), maximum = Math.max(...values);
        const average = values.reduce((total, value) => total + value, 0) / values.length;
        // Same extrema priority as the detail table; average uses displayed days.
        // Hiển thị mỗi ngày trong danh sách
        recentData.forEach(day => {
            const consumption = day["Điện tiêu thụ (kWh)"];

            // Format date nicely
            const date = new Date(day.Ngày.split('-').reverse().join('-'));
            const formattedDate = date.toLocaleDateString('vi-VN', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });

            const consumptionClass = consumption === maximum ? 'recent-maximum'
                : consumption === minimum ? 'recent-minimum'
                : consumption <= average ? 'recent-below-average' : 'recent-above-average';
            const icon = consumption === maximum ? '↑' : consumption === minimum ? '↓' : '•';

            const dayElement = document.createElement('div');
            dayElement.className = 'recent-day-item';
            dayElement.innerHTML = `
                <span class="date"><span class="icon">${icon}</span>${formattedDate}</span>
                <span class="consumption ${consumptionClass}">${consumption.toFixed(2)} kWh</span>
            `;

            recentDaysContainer.appendChild(dayElement);
        });
    }

    // Kiểm tra localStorage có khả dụng không
    isLocalStorageAvailable() {
        try {
            const testKey = '__test__';
            localStorage.setItem(testKey, '1');
            localStorage.removeItem(testKey);
            return true;
        } catch (e) {
            return false;
        }
    }

    // Detect if running inside Home Assistant frontend
    isHomeAssistantEnv() {
        try {
            // Heuristic: running in iframe and URL contains 'lovelace' or 'home-assistant' or 'hass'
            const inIframe = window.parent && window.parent !== window;
            const url = window.location.href;
            return (
                inIframe &&
                (/lovelace|home-assistant|hass/i.test(url) || window.parent.hass !== undefined)
            );
        } catch (e) {
            return false;
        }
    }
}

// Export cho sử dụng global
window.UIManager = UIManager;
