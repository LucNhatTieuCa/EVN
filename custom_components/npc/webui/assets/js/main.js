// Main Application Logic
class ElectricityApp {
    constructor() {
        this.dataManager = new DataManager();
        this.chartManager = new ChartManager();
        this.uiManager = new UIManager();
        this.currentYear = new Date().getFullYear();

        this.init();
    } async init() {
        try {
            this.uiManager.showLoader(true);
            await this.loadAccounts();
            this.setupEventListeners();

            // Khởi tạo ô kết quả tìm kiếm với thông báo mặc định
            this.uiManager.initializeSearchResults();

            // Delay restore để đảm bảo tất cả select elements đã được populate và DOM stable
            setTimeout(async () => {
                this.restoreUIState();
                // Trigger load data after restore để đảm bảo data sync với UI
                await this.loadDataForAccount();
            }, 500);
        } catch (error) {
            console.error('Lỗi khởi tạo ứng dụng:', error);
            this.uiManager.showToast('Không thể khởi tạo ứng dụng. Vui lòng kiểm tra kết nối và thử lại.', 'error');
        } finally {
            this.uiManager.showLoader(false);
        }
    } async loadAccounts() {
        try {
            const accounts = await this.dataManager.loadAccounts();
            this.uiManager.populateAccountSelect(accounts);
        } catch (error) {
            console.error('Lỗi tải danh sách tài khoản:', error);
            this.uiManager.showToast('Không thể tải danh sách tài khoản từ options.json. Kiểm tra file và server.', 'error');
        }
    } async loadDataForAccount() {
        this.uiManager.showLoader(true);
        try {
            const accountSelect = document.getElementById('accountSelect');
            const account = accountSelect.value;
            this.uiManager.updateCustomerHeader();

            if (!account) {
                this.uiManager.clearData();
                this.chartManager.destroyCharts();
                // Reset billing cycle display to default

                return;
            }

            const data = await this.dataManager.loadDataForAccount(account);
            this.processAndDisplayData();
            this.uiManager.updateAccountAvatar(account);
        } catch (error) {
            console.error('Lỗi tải dữ liệu:', error);
        } finally {
            this.uiManager.showLoader(false);
        }
    } processAndDisplayData() {
        // Lấy tất cả các năm có sẵn trong dữ liệu
        const availableYears = this.dataManager.getAvailableYears();
        this.uiManager.populateYearSelect(availableYears);

        // Cập nhật dropdown tháng (đã lọc theo năm nếu có)
        const uniqueMonths = this.dataManager.getUniqueMonths(this.currentYear);
        this.uiManager.populateMonthSelect(uniqueMonths);

        // Tính toán và hiển thị summary (đã lọc theo năm)
        const summary = this.dataManager.calculateSummary(this.currentYear);
        this.uiManager.updateSummaryNumbers(summary);



        // Tạo summary cards với trend (có thể thay đổi số 4 thành số khác)
        const recentMonths = uniqueMonths.slice(0, 4); // 4 tháng gần nhất
        const trendData = this.dataManager.calculateTrendData(recentMonths);
        this.uiManager.renderSummaryContainer(trendData);        // Tạo biểu đồ monthly (đã lọc theo năm)
        const filteredMonthlyData = this.dataManager.getFilteredMonthlyData(this.currentYear);
        this.chartManager.createMonthlyChart(
            filteredMonthlyData,
            summary.currentPeriod,
            (evt, elements) => this.handleMonthlyChartClick(evt, elements)
        );

        // Tạo biểu đồ daily ban đầu
        const initialMonth = uniqueMonths[0];
        const initialDailyData = this.dataManager.getDataByMonth(initialMonth);
        this.chartManager.createDailyChart(initialDailyData);

        // Hiển thị 7 ngày gần đây trong card tìm kiếm
        const recentDays = this.getRecentSevenDays();
        this.uiManager.displayRecentDays(recentDays);
    }

    getRecentSevenDays() {
        // Seven calendar days ending at the latest actual EVN usage day.
        const dayNumber = row => {
            const [day, month, year] = String(row.Ngày || '').split('-').map(Number);
            return Date.UTC(year, month - 1, day);
        };
        const rows = (this.dataManager.dailyData || []).filter(row => Number.isFinite(dayNumber(row)));
        if (!rows.length) return [];
        const end = Math.max(...rows.map(dayNumber));
        return rows.filter(row => dayNumber(row) >= end - 6 * 86400000 && dayNumber(row) <= end)
            .sort((a, b) => dayNumber(a) - dayNumber(b));
    }

    handleMonthlyChartClick(evt, elements) {
        if (elements && elements.length > 0) {
            const idx = elements[0].index;
            const monthLabel = this.chartManager.monthlyChart.data.labels[idx];


            let filteredDailyData;
            let targetMonth;            // Kiểm tra xem có phải "Kỳ này" không
            if (monthLabel.includes('Kỳ này')) {
                // Lấy tháng hiện tại từ uniqueMonths - đã được xử lý đúng ở data.js
                const uniqueMonths = this.dataManager.getUniqueMonths();
                targetMonth = uniqueMonths[0]; // "Kỳ này" thường ở index 0

                filteredDailyData = this.dataManager.getDataByMonth(targetMonth);
            } else {
                // Lấy tháng từ label ("Tháng 05-2025" hoặc "T05-2025")
                const monthMatch = monthLabel.match(/(?:Tháng|T)\s*[-]?\s*(\d{1,2})/i);
                if (monthMatch) {
                    const monthNum = monthMatch[1].padStart(2, '0');
                    targetMonth = `${monthNum}-${this.currentYear}`;
                    filteredDailyData = this.dataManager.getDataByMonth(targetMonth);
                }
            }

            if (filteredDailyData) {
                this.chartManager.createDailyChart(filteredDailyData);

                // Scroll tới daily chart
                document.getElementById('dailyChart').scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            } else {
                console.error('❌ No data found for clicked period:', monthLabel);
            }
        }
    }

    setupEventListeners() {
        // Resize listener
        window.addEventListener('resize', () => {
            if (this.dataManager.currentAccount) {
                clearTimeout(this.resizeTimeout);
                this.resizeTimeout = setTimeout(() => {
                    this.processAndDisplayData();
                }, 250);
            }
        });

        // Account select change
        const accountSelect = document.getElementById('accountSelect');
        if (accountSelect) {
            accountSelect.addEventListener('change', () => {
                this.loadDataForAccount();
                this.saveUIState(); // Save state on account change
            });
        }

        // Month select change
        const monthSelect = document.getElementById('monthSelect');
        if (monthSelect) {
            monthSelect.addEventListener('change', (e) => {
                const filteredDailyData = this.dataManager.getDataByMonth(e.target.value);
                this.chartManager.createDailyChart(filteredDailyData);
                this.saveUIState(); // Save state on month change
            });
        }

        // Year select change
        const yearSelect = document.getElementById('yearSelect');
        if (yearSelect) {
            yearSelect.addEventListener('change', (e) => {
                const selectedYear = e.target.value;
                this.currentYear = selectedYear === 'all' ? null : parseInt(selectedYear);
                this.processAndDisplayData();
                this.saveUIState(); // Save state on year change
            });
        }        // Search functionality
        const searchBtn = document.getElementById('searchBtn');
        if (searchBtn) {
            searchBtn.addEventListener('click', () => this.handleSearch());
        }        // Date inputs
        const startDate = document.getElementById('startDate');
        const endDate = document.getElementById('endDate');
        if (startDate && endDate) {
            // Set default dates
            const today = new Date();
            const sevenDaysAgo = new Date(today);
            sevenDaysAgo.setDate(today.getDate() - 7);
            sevenDaysAgo.setHours(0, 0, 0, 0);

            endDate.value = today.toISOString().split('T')[0];
            startDate.value = sevenDaysAgo.toISOString().split('T')[0];

            // Add event listeners to save state on change
            startDate.addEventListener('change', () => this.saveUIState());
            endDate.addEventListener('change', () => this.saveUIState());

            // Hiển thị dữ liệu 7 ngày gần đây khi trang được tải
            setTimeout(() => {
                if (this.dataManager && this.dataManager.dailyData && this.dataManager.dailyData.length > 0) {
                    // Lấy dữ liệu 7 ngày gần đây
                    const filteredData = this.getRecentSevenDays();

                    if (filteredData.length > 0) {
                        // Cập nhật biểu đồ
                        this.chartManager.createDailyChart(filteredData);

                        // Hiển thị dữ liệu trong card tìm kiếm
                        this.uiManager.displayRecentDays(filteredData);
                    }
                }
            }, 1000); // Delay 1 second to ensure data is loaded
        }

        document.addEventListener('evn-history-updated',()=>this.loadDataForAccount());

        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => this.handleFilterClick(btn));
        });        // Detail table toggle
        const toggleDetailTable = document.getElementById('toggleDetailTable');
        if (toggleDetailTable) {
            toggleDetailTable.addEventListener('click', () => this.toggleDetailTable());
        }

        // Modal event listeners - delay để đảm bảo DOM đã load
        setTimeout(() => {
            this.setupModalEventListeners();
        }, 100);

        // Summary month cards click handling
        this.setupSummaryCardsClickHandler();        // Trang được tải sẽ tự động hiển thị 7 ngày gần nhất (đã xử lý trong setup date inputs)
    } handleSearch() {
        const searchBtn = document.getElementById('searchBtn');
        const startDateInput = document.getElementById('startDate');
        const endDateInput = document.getElementById('endDate');

        // Add loading effect to button
        if (searchBtn) {
            searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xử lý...';
            searchBtn.disabled = true;
        }

        const startDate = new Date(startDateInput.value);
        const endDate = new Date(endDateInput.value);

        if (isNaN(startDate) || isNaN(endDate)) {
            this.uiManager.showToast('Vui lòng chọn ngày bắt đầu và ngày kết thúc hợp lệ!', 'error');
            if (searchBtn) {
                searchBtn.innerHTML = '<i class="fas fa-search"></i> Tìm kiếm';
                searchBtn.disabled = false;
            }
            return;
        }

        if (startDate > endDate) {
            this.uiManager.showToast('Ngày bắt đầu không thể lớn hơn ngày kết thúc!', 'error');
            if (searchBtn) {
                searchBtn.innerHTML = '<i class="fas fa-search"></i> Tìm kiếm';
                searchBtn.disabled = false;
            }
            return;
        }

        // Lọc dữ liệu
        const filteredData = this.dataManager.getDataByDateRange(startDate, endDate);

        if (filteredData.length === 0) {
            this.uiManager.showToast('Không có dữ liệu trong khoảng thời gian đã chọn', 'error');
            if (searchBtn) {
                searchBtn.innerHTML = '<i class="fas fa-search"></i> Tìm kiếm';
                searchBtn.disabled = false;
            }
            return;
        }

        // Tính tổng cho khoảng thời gian
        const totalConsumptionInRange = filteredData.reduce((sum, day) =>
            sum + day["Điện tiêu thụ (kWh)"], 0
        );

        // Cập nhật biểu đồ
        this.chartManager.createDailyChart(filteredData);

        // Mở popup chi tiết tiêu thụ điện - chỉ khi người dùng bấm tìm kiếm
        // Mở modal khi đây là hành động chủ động từ người dùng, không phải tự động lúc tải trang
        if (searchBtn) {
            this.openDetailModal(true);

            // Hiển thị dữ liệu trong bảng chi tiết
            this.renderDetailTable(filteredData);
        }

        // Hiển thị thông báo thành công
        this.uiManager.showToast(`Đã tìm thấy ${filteredData.length} ngày với tổng tiêu thụ ${totalConsumptionInRange.toFixed(2)} kWh`, 'success');
        // Hiển thị lại dữ liệu gần đây sau khi tìm kiếm
        const recentDays = this.getRecentSevenDays();
        this.uiManager.displayRecentDays(recentDays);

        // Reset button state
        if (searchBtn) {
            searchBtn.innerHTML = '<i class="fas fa-search"></i> Tìm kiếm';
            searchBtn.disabled = false;
        }
    }

    handleFilterClick(btn) {
        const days = parseInt(btn.dataset.range);
        const sorted = [...this.dataManager.dailyData].sort((a, b) =>
            new Date(b.Ngày.split('-').reverse().join('-')) -
            new Date(a.Ngày.split('-').reverse().join('-'))
        );
        const filtered = sorted.filter(d => d["Điện tiêu thụ (kWh)"] > 0)
            .slice(0, days)
            .reverse();

        this.chartManager.createDailyChart(filtered);
        this.renderDetailTable(filtered);
    } toggleDetailTable() {
        // Mở popup modal thay vì toggle bảng trong card
        this.openDetailModal(false);
    } openDetailModal(fromSearch = true) {
        const modal = document.getElementById('detailModal');
        if (!modal) {
            console.error('Modal element not found');
            return;
        }

        // Update modal title based on context
        const modalTitle = modal.querySelector('.modal-title');
        if (modalTitle) {
            if (fromSearch) {
                const startDate = document.getElementById('startDate')?.value;
                const endDate = document.getElementById('endDate')?.value;
                if (startDate && endDate) {
                    const formattedStart = new Date(startDate).toLocaleDateString('vi-VN');
                    const formattedEnd = new Date(endDate).toLocaleDateString('vi-VN');
                    modalTitle.innerHTML = `Chi Tiết Tiêu Thụ Điện (${formattedStart} - ${formattedEnd})`;
                } else {
                    modalTitle.innerHTML = 'Chi Tiết Tiêu Thụ Điện';
                }
            } else {
                modalTitle.innerHTML = 'Chi Tiết Tiêu Thụ Điện';
            }
        }

        modal.classList.add('show');
        document.body.style.overflow = 'hidden'; // Prevent scrolling behind modal

        // Render lại bảng với dữ liệu hiện tại
        const currentData = this.getCurrentDisplayData();
        this.renderDetailTable(currentData);
    }

    closeDetailModal() {
        const modal = document.getElementById('detailModal');
        if (!modal) {
            console.error('Modal element not found');
            return;
        }

        modal.classList.remove('show');
        document.body.style.overflow = ''; // Restore scrolling
    } getCurrentDisplayData() {
        // Lấy dữ liệu hiện tại đang hiển thị trên daily chart
        if (this.chartManager && this.chartManager.dailyChart && this.chartManager.dailyChart.data) {
            // Lấy từ daily chart data đang hiển thị
            const chartData = this.chartManager.dailyChart.data;
            const labels = chartData.labels || [];
            const dataPoints = chartData.datasets[0]?.data || [];


            // Tạo array data từ chart hiện tại
            const currentData = labels.map((label, index) => {
                return {
                    'Ngày': label,
                    'Điện tiêu thụ (kWh)': dataPoints[index] || 0,
                    'Tiền điện': null // Sẽ tính sau nếu cần
                };
            });

            return currentData;
        }

        // Fallback: Lấy từ month select như cũ
        const selectedMonth = document.getElementById('monthSelect')?.value;
        if (!selectedMonth || !this.dataManager) {
            return [];
        }
        return this.dataManager.getDataByMonth(selectedMonth);
    } async renderDetailTable(data) {
        const requestId = (this._pricingRequest || 0) + 1;
        this._pricingRequest = requestId;
        const account = this.currentAccount || this.dataManager.currentAccount;
        await this.loadDailyPricing(account);
        if (requestId !== this._pricingRequest || account !== (this.currentAccount || this.dataManager.currentAccount)) return;
        const tbody = document.querySelector('#detailTable tbody');
        const statsContainer = document.getElementById('tableStats');
        if (!tbody) return;

        tbody.innerHTML = '';
        document.getElementById('detailPriceNote')?.remove();
        if (statsContainer) statsContainer.innerHTML = '';
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-gray-400">Không có dữ liệu</td></tr>';
            if (statsContainer) {
                statsContainer.innerHTML = '<div class="text-center text-gray-400">Không có dữ liệu để thống kê</div>';
            }
            return;
        }

        // Lọc dữ liệu chỉ hiển thị ngày có tiêu thụ > 0
        const validData = data.filter(d => d["Điện tiêu thụ (kWh)"] > 0);
        if (validData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-gray-400">Không có dữ liệu tiêu thụ</td></tr>';
            if (statsContainer) {
                statsContainer.innerHTML = '<div class="text-center text-gray-400">Không có dữ liệu tiêu thụ để thống kê</div>';
            }
            return;
        }

        // Sắp xếp dữ liệu theo thứ tự thời gian để tính bậc thang tích lũy
        const sortedData = [...validData].sort((a, b) => {
            const dateA = new Date(a.Ngày.split('-').reverse().join('-'));
            const dateB = new Date(b.Ngày.split('-').reverse().join('-'));
            return dateA - dateB;
        });

        // Tính toán tiền điện theo bậc thang tích lũy
        const dataWithCosts = this.calculateDailyCostWithTiers(sortedData);

        // Highlight max/min
        const vals = dataWithCosts.map(d => d.kwh);
        const max = Math.max(...vals);
        const min = Math.min(...vals);
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        const totalKwh = vals.reduce((a, b) => a + b, 0);
        const pricesComplete = dataWithCosts.every(day=>day.dailyCost!==null);
        const totalCost = pricesComplete ? dataWithCosts.reduce((sum, d) => sum + d.dailyCost, 0) : null;
        const money = value=>value===null?'Chưa đủ dữ liệu':Number(value).toLocaleString('vi-VN')+' VNĐ';
        const unit = value=>value===null?'Chưa đủ dữ liệu':Number(value).toFixed(0)+' VNĐ/kWh';

        const legend = document.getElementById('detailColorLegend') || document.createElement('p');
        legend.id = 'detailColorLegend';
        legend.className = 'detail-color-legend';
        legend.innerHTML = '<span class="highlight-min">Thấp nhất</span> · <span class="highlight-below-average">Dưới TB</span> · <span class="highlight-above-average">Trên TB</span> · <span class="highlight-max">Cao nhất</span>';
        const averageLabel = document.createElement('span');
        averageLabel.className = 'detail-average-value';
        averageLabel.textContent = `Trung bình: ${avg.toLocaleString('vi-VN', {maximumFractionDigits: 2})} kWh/ngày`;
        legend.appendChild(averageLabel);
        document.getElementById('detailTable').before(legend);
        const priceNote=document.getElementById('detailPriceNote')||document.createElement('details');
        priceNote.id='detailPriceNote';priceNote.className='detail-price-note';
        const periodKeys=[...new Set(dataWithCosts.map(day=>day.period).filter(Boolean))];
        const period=periodKeys.length===1?this._dailyPricing?.periods?.[periodKeys[0]]:null;
        const vatRates=[...new Set(dataWithCosts.map(day=>day.vat).filter(v=>v!=null))];
        const vatText=vatRates.length===1?vatRates[0]+'%':'theo từng kỳ';
        let note=`Tiền dự kiến theo biểu giá sinh hoạt đang cấu hình; tiền và đơn giá bình quân đã gồm VAT ${vatText}. Tiền ngày = tiền lũy kế hết ngày − tiền lũy kế trước ngày, theo chỉ số gốc kỳ EVN; lọc ngày không tính lại bậc từ 0.`;
        if(periodKeys.length>1)note+=' Các ngày thuộc nhiều kỳ: bậc thang được tính riêng theo từng kỳ.';
        if(period?.total) note+=` Gốc kỳ: ${period.baseline_index.toLocaleString('vi-VN')} kWh. Cả kỳ đến ${period.total.through_day}: ${period.total.kwh.toLocaleString('vi-VN')} kWh · ${money(period.total.estimated_vnd)}.`;
        if(period?.opening?.kwh>0) note+=` Phần đầu kỳ trước dữ liệu ngày ${period.opening.before_day}: ${period.opening.kwh.toLocaleString('vi-VN')} kWh · ${money(period.opening.estimated_vnd)}; đã cộng khi xác định bậc, không cộng vào tổng tiền các ngày đang chọn.`;
        const invoiceCheck=periodKeys.length===1?this._dailyPricing?.period_checks?.[periodKeys[0]]:null;
        if(invoiceCheck?.status==='matched') note+=` Đã đối chiếu tổng tiền và VAT hóa đơn ${invoiceCheck.invoice_period}.`;
        if(invoiceCheck?.pdf_period) note+=` Bậc ${invoiceCheck.confirmed_pdf_tiers.join(', ')} đối chiếu bảng tiền điện ${invoiceCheck.pdf_period}; các bậc còn lại theo biểu giá EVN được ghi nguồn.`;
        if(invoiceCheck?.status==='invoice_tariff_mismatch') note+=' Hóa đơn mới khác biểu giá đang dùng: tạm ngừng ước tính, cần xác minh đơn giá trước khi cập nhật.';
        note+=' Khi EVN cập nhật hóa đơn, hệ thống đối chiếu lại tổng tiền/VAT. Tiền ngày làm tròn bằng chênh lệch tổng lũy kế, có thể lệch 1đ so với làm tròn từng dòng bậc.';
        if(!pricesComplete) note+=' Ngày thiếu gốc kỳ/chỉ số đối chiếu được để trống tiền, không tính lại từ bậc 1.';
        if(invoiceCheck?.official_tariff_source) note+=' Biểu giá: Quyết định 1279/QĐ-BCT, hiệu lực 10/05/2025.';
        priceNote.replaceChildren();
        const priceSummary=document.createElement('summary');
        priceSummary.textContent=`Đã gồm VAT ${this._dailyPricing?.vat_percent??8}% · Bậc tính theo điện lũy kế · Chi tiết cách tính`;
        const priceBody=document.createElement('p');priceBody.textContent=note;
        priceNote.append(priceSummary,priceBody);document.getElementById('detailTable').before(priceNote);


        // Hiển thị dữ liệu trong bảng
        dataWithCosts.forEach(dayData => {
            const { date, kwh, dailyCost, avgTierPrice, tierParts, isMax, isMin } = dayData;
            const tierDescription=tierParts.map(part=>`Bậc ${Number(part.tier)}: ${Number(part.kwh).toLocaleString('vi-VN',{maximumFractionDigits:3})} kWh × ${Number(part.unit_with_vat).toLocaleString('vi-VN',{minimumFractionDigits:0,maximumFractionDigits:2})} đ/kWh`).join('<br>');

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="px-2 py-1">${date}</td>
                <td class="px-2 py-1 ${isMax ? 'highlight-max' : isMin ? 'highlight-min' : kwh <= avg ? 'highlight-below-average' : 'highlight-above-average'}">${kwh.toFixed(2)}</td>
                <td class="px-2 py-1">${money(dailyCost)}</td>
                <td class="px-2 py-1">TB: ${unit(avgTierPrice)}<small class="tier-parts">${tierDescription || 'Chưa xác nhận bậc giá'}</small></td>
            `;
            tbody.appendChild(tr);
        });

        // Hiển thị thống kê ở phần cố định
        if (statsContainer) {
            const maxData = dataWithCosts.find(d => d.kwh === max);
            const minData = dataWithCosts.find(d => d.kwh === min);

            statsContainer.innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <!-- Thống kê tổng quan -->
                    <div class="evn-summary-overview bg-purple-900 bg-opacity-50 p-3 rounded-lg">
                        <h4 class="font-bold text-blue-300 mb-2 flex items-center">
                            <i class="fas fa-chart-bar mr-2"></i>📊 Tổng quan
                        </h4>
                        <div class="space-y-1 text-xs">
                            <div><strong>Tổng:</strong> ${totalKwh.toFixed(2)} kWh</div>
                            <div><strong>TB:</strong> ${avg.toFixed(2)} kWh/ngày</div>
                            <div><strong>Tiền:</strong> ${money(totalCost)}</div>
                            <div><strong>TB:</strong> ${totalCost===null?'Chưa đủ dữ liệu':Math.round(totalCost/dataWithCosts.length).toLocaleString('vi-VN')+' VNĐ/ngày'}</div>
                            <div><strong>Số ngày:</strong> ${dataWithCosts.length} ngày</div>
                        </div>
                    </div>
                    
                    <!-- Max -->
                    <div class="evn-summary-high bg-red-900 bg-opacity-50 p-3 rounded-lg">
                        <h4 class="font-bold text-red-300 mb-2 flex items-center">
                            <i class="fas fa-arrow-up mr-2"></i>📈 Cao nhất
                        </h4>
                        <div class="space-y-1 text-xs">
                            <div><strong>Ngày:</strong> ${maxData ? maxData.date : '-'}</div>
                            <div><strong>Tiêu thụ:</strong> <span class="highlight-max">${max.toFixed(2)} kWh</span></div>
                            <div><strong>Tiền:</strong> ${maxData ? money(maxData.dailyCost) : '-'}</div>
                            <div><strong>Giá:</strong> ${maxData ? unit(maxData.avgTierPrice) : '-'}</div>
                        </div>
                    </div>
                    
                    <!-- Min -->
                    <div class="evn-summary-low bg-blue-900 bg-opacity-50 p-3 rounded-lg">
                        <h4 class="font-bold text-blue-300 mb-2 flex items-center">
                            <i class="fas fa-arrow-down mr-2"></i>📉 Thấp nhất
                        </h4>
                        <div class="space-y-1 text-xs">
                            <div><strong>Ngày:</strong> ${minData ? minData.date : '-'}</div>
                            <div><strong>Tiêu thụ:</strong> <span class="highlight-min">${min.toFixed(2)} kWh</span></div>
                            <div><strong>Tiền:</strong> ${minData ? money(minData.dailyCost) : '-'}</div>
                            <div><strong>Giá:</strong> ${minData ? unit(minData.avgTierPrice) : '-'}</div>
                        </div>
                    </div>
                </div>
            `;
        }
    }

    // Hàm tính toán tiền điện theo bậc thang tích lũy đúng cách
    async loadDailyPricing(account) {
        if (this._dailyPricing?.account === account && Date.now()-this._dailyPricingAt < 60000) return;
        try {
            let ha;try {ha=window.parent.document.querySelector('home-assistant')?.hass;} catch (_) {}
            let result;
            if (ha?.callApi) result=await ha.callApi('GET',`npc/pricing/${encodeURIComponent(account)}`);
            else {
                const token=JSON.parse(localStorage.getItem('hassTokens')||'null')?.access_token;
                if(!token) throw new Error('login_required');
                const response=await fetch(`/api/npc/pricing/${encodeURIComponent(account)}`,{headers:{Authorization:`Bearer ${token}`}});
                if(!response.ok)throw new Error('pricing_unavailable');
                result=await response.json();
            }
            this._dailyPricing=result;this._dailyPricingAt=Date.now();
        } catch (_) {this._dailyPricing={account,daily:{},status:'unavailable'};this._dailyPricingAt=0;}
    }

    calculateDailyCostWithTiers(sortedData) {
        const vals=sortedData.map(day=>Number(day['Điện tiêu thụ (kWh)']));
        const maximum=Math.max(...vals),minimum=Math.min(...vals);
        return sortedData.map(day=>{
            const kwh=Number(day['Điện tiêu thụ (kWh)']);
            const priced=this._dailyPricing?.daily?.[day.Ngày];
            const valid=priced && Math.abs(priced.kwh-kwh)<0.00001;
            return {date:day.Ngày,kwh,dailyCost:valid?priced.daily_cost_vnd:null,
                avgTierPrice:valid?priced.average_unit_vnd:null,tierParts:valid?(priced.tier_parts||[]):[],
                cumulativeKwh:valid?priced.cumulative_after_kwh:null,period:valid?priced.period:null,vat:valid?priced.vat_percent:null,isMax:kwh===maximum,isMin:kwh===minimum};
        });
    }

    // Setup event listeners cho summary month cards
    setupSummaryCardsClickHandler() {
        // Sử dụng event delegation để handle click cho các cards động
        const summaryContainer = document.getElementById('summaryContainer');
        if (summaryContainer) {
            summaryContainer.addEventListener('click', (e) => {
                // Tìm summary card được click
                const summaryCard = e.target.closest('.summary-month-card');
                if (summaryCard) {
                    this.handleSummaryCardClick(summaryCard);
                }
            });
        }
    }    // Xử lý click vào summary month card
    handleSummaryCardClick(card) {

        const cardId = card.id;
        const cardIndex = cardId.replace('summary-month-', '');

        // Lấy dữ liệu tháng tương ứng
        const uniqueMonths = this.dataManager.getUniqueMonths();
        const targetMonth = uniqueMonths[parseInt(cardIndex)];

        if (targetMonth) {
            // Kiểm tra xem có phải "Kỳ này" không
            const cardTitle = card.querySelector('h4');
            const isCurrentPeriod = cardTitle && cardTitle.textContent.includes('Kỳ này');
            let filteredDailyData; if (isCurrentPeriod) {
                // Lấy dữ liệu theo chu kỳ thanh toán hiện tại - logic đã được xử lý ở data.js
                filteredDailyData = this.dataManager.getDataByMonth(targetMonth);
            } else {
                // Lấy dữ liệu theo tháng thông thường
                filteredDailyData = this.dataManager.getDataByMonth(targetMonth);
            }

            // Cập nhật daily chart
            this.chartManager.createDailyChart(filteredDailyData);

            // Scroll tới daily chart
            const dailyChart = document.getElementById('dailyChart');
            if (dailyChart) {
                dailyChart.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        } else {
            console.error('❌ Target month not found for index:', cardIndex);
        }
    } setupModalEventListeners() {
        const modal = document.getElementById('detailModal');
        const closeBtn = document.getElementById('modalCloseBtn');

        if (!modal) {
            console.error('Modal element not found in setupModalEventListeners');
            return;
        }

        // Close button event listener
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.closeDetailModal();
            });
        }

        // Đóng modal khi click outside
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeDetailModal();
            }
        });

        // Đóng modal khi nhấn ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('show')) {
                this.closeDetailModal();
            }
        });
    }

    // Save current UI state to localStorage
    saveUIState() {
        const accountSelect = document.getElementById('accountSelect');
        const monthSelect = document.getElementById('monthSelect');
        const yearSelect = document.getElementById('yearSelect');
        const startDate = document.getElementById('startDate');
        const endDate = document.getElementById('endDate');

        const state = {
            selectedAccount: accountSelect?.value || '',
            selectedMonth: monthSelect?.value || '',
            selectedYear: yearSelect?.value || 'all',
            startDate: startDate?.value || '',
            endDate: endDate?.value || ''
        };

        localStorage.setItem('uiState', JSON.stringify(state));
    }

    // Restore UI state from localStorage
    restoreUIState() {
        try {
            const savedState = localStorage.getItem('uiState');
            if (!savedState) return;

            const state = JSON.parse(savedState);

            // Restore account selection
            const accountSelect = document.getElementById('accountSelect');
            if (accountSelect && state.selectedAccount) {
                accountSelect.value = state.selectedAccount;
            }

            // Restore year selection
            const yearSelect = document.getElementById('yearSelect');
            if (yearSelect && state.selectedYear) {
                yearSelect.value = state.selectedYear;
                this.currentYear = state.selectedYear === 'all' ? null : parseInt(state.selectedYear);
            }

            // Restore month selection
            const monthSelect = document.getElementById('monthSelect');
            if (monthSelect && state.selectedMonth) {
                monthSelect.value = state.selectedMonth;
            }

            // Restore date inputs
            const startDate = document.getElementById('startDate');
            const endDate = document.getElementById('endDate');
            if (startDate && state.startDate) {
                startDate.value = state.startDate;
            }
            if (endDate && state.endDate) {
                endDate.value = state.endDate;
            }

        } catch (error) {
            console.error('❌ Error restoring UI state:', error);
        }
    }
}

// Khởi tạo ứng dụng khi DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ElectricityApp();
});

// Export cho global access
window.ElectricityApp = ElectricityApp;
